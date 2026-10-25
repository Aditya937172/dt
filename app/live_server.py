import asyncio
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.session_store import list_sessions, replay_window


class LiveServer:
    def __init__(self, port):
        self.lock = threading.Lock()
        self.state = {"frame_id": 0, "hands": [], "robot_hands": [], "status": "STARTING"}
        self.jpeg = b""
        self.commands = []
        app = FastAPI()
        root = Path(__file__).resolve().parent.parent / "web"

        @app.get("/")
        def index():
            return FileResponse(root / "index.html")

        @app.get("/api/state")
        def state():
            with self.lock:
                return self.state

        @app.get("/api/preview")
        def preview():
            with self.lock:
                return Response(self.jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

        @app.post("/api/record/{action}")
        def record(action: str):
            if action not in ("start", "stop"):
                return Response(status_code=400)
            with self.lock:
                self.commands.append(action)
            return {"queued": action}

        @app.post("/api/fsr/calibrate")
        def calibrate_fsr():
            with self.lock:
                self.commands.append("calibrate-fsr")
            return {"queued": "calibrate-fsr"}

        @app.post("/api/fsr/calibrate-pressed")
        def calibrate_pressed_fsr():
            with self.lock:
                self.commands.append("calibrate-fsr-pressed")
            return {"queued": "calibrate-fsr-pressed"}

        @app.get("/api/sessions")
        def sessions():
            return list_sessions()

        @app.get("/api/sessions/{session_id}/replay")
        def replay(session_id: int, start_ms: float = 0, duration_ms: float = 20000):
            result = replay_window(session_id, start_ms, duration_ms)
            if result is None:
                raise HTTPException(status_code=404, detail="Session not found")
            return result

        @app.get("/api/sessions/{session_id}/video")
        def session_video(session_id: int):
            path = Path("sessions") / f"session_{session_id:03d}" / "camera.mp4"
            if not path.is_file():
                raise HTTPException(status_code=404, detail="Video not available")
            return FileResponse(path, media_type="video/mp4")

        @app.websocket("/ws")
        async def websocket(ws: WebSocket):
            await ws.accept()
            try:
                while True:
                    # Client requests the next state after rendering: one message in flight.
                    message = await ws.receive_json()
                    if message.get("type") == "ping":
                        await ws.send_json({"type": "pong", "client_ms": message["client_ms"],
                                            "server_ms": time.time() * 1000})
                        continue
                    with self.lock:
                        newest = dict(self.state)
                    newest["sent_unix_ms"] = time.time() * 1000
                    await ws.send_json(newest)
            except (WebSocketDisconnect, RuntimeError):
                pass

        app.mount("/static", StaticFiles(directory=root), name="static")
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not self.server.started:
            raise RuntimeError("Local server could not start; choose another --port")

    def publish(self, state, jpeg):
        with self.lock:
            self.state, self.jpeg = state, jpeg

    def take_commands(self):
        with self.lock:
            commands, self.commands = self.commands, []
        return commands

    def close(self):
        self.server.should_exit = True
        self.thread.join(timeout=3)
