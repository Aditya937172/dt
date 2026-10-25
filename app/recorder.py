from __future__ import annotations

import json
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionRecorder:
    def __init__(self, root: str | Path = "sessions") -> None:
        self.root = Path(root)
        self.session_dir: Path | None = None
        self.data_file = None
        self.robot_file = None
        self.fsr_file = None
        self.events_file = None
        self.video_index_file = None
        self.video_writer = None
        self.video_queue: queue.Queue | None = None
        self.video_thread: threading.Thread | None = None
        self.video_error: str | None = None
        self.dropped_video_frames = 0
        self.video_frame_count = 0
        self.video_origin_ms: float | None = None
        self.video_fps = 30.0
        self.last_video_frame = None
        self.last_video_frame_id = 0
        self.db: sqlite3.Connection | None = None
        self.session_id: int | None = None
        self.last_commit = 0.0
        self.frame_count = 0
        self.fsr_sample_count = 0

    @property
    def is_recording(self) -> bool:
        return self.data_file is not None

    def start(self, metadata: dict[str, Any]) -> Path:
        if self.is_recording:
            return self.session_dir  # type: ignore[return-value]

        self.root.mkdir(parents=True, exist_ok=True)
        existing = [
            path for path in self.root.glob("session_*")
            if path.is_dir() and path.name.removeprefix("session_").isdigit()
        ]
        next_id = (max([int(path.name.removeprefix("session_")) for path in existing], default=0) + 1)
        self.session_dir = self.root / f"session_{next_id:03d}"
        self.session_dir.mkdir()

        metadata = dict(metadata)
        metadata["recording_start_wall_time_utc"] = datetime.now(timezone.utc).isoformat()
        with (self.session_dir / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        with (self.session_dir / "calibration.json").open("w", encoding="utf-8") as f:
            json.dump(metadata.get("calibration", {"status": "missing"}), f, indent=2)

        self.data_file = (self.session_dir / "hand_landmarks.jsonl").open("a", encoding="utf-8")
        self.robot_file = (self.session_dir / "robot_hand_state.jsonl").open("a", encoding="utf-8")
        self.fsr_file = (self.session_dir / "fsr.jsonl").open("a", encoding="utf-8")
        self.events_file = (self.session_dir / "events.jsonl").open("a", encoding="utf-8")
        self.db = sqlite3.connect(self.root / "captures.sqlite")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY,
                started_utc TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                frame_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS frames (
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                frame_id INTEGER NOT NULL,
                session_time_ms REAL NOT NULL,
                hands_json TEXT NOT NULL,
                pose_json TEXT NOT NULL,
                grasp_state TEXT,
                robot_json TEXT,
                PRIMARY KEY (session_id, frame_id)
            );
            CREATE TABLE IF NOT EXISTS fsr_samples (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                session_time_ms REAL NOT NULL,
                esp_timestamp_us INTEGER NOT NULL,
                fsr1_raw INTEGER NOT NULL,
                fsr2_raw INTEGER NOT NULL,
                thumb_pressure REAL,
                index_pressure REAL,
                quality TEXT NOT NULL DEFAULT 'uncalibrated',
                CHECK (fsr1_raw BETWEEN 0 AND 4095),
                CHECK (fsr2_raw BETWEEN 0 AND 4095)
            );
            CREATE INDEX IF NOT EXISTS fsr_by_time ON fsr_samples(session_id, session_time_ms);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                session_time_ms REAL NOT NULL,
                event TEXT NOT NULL,
                source TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_by_time ON events(session_id, session_time_ms);
            CREATE TABLE IF NOT EXISTS video_frames (
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                video_frame_index INTEGER NOT NULL,
                frame_id INTEGER NOT NULL,
                session_time_ms REAL NOT NULL,
                PRIMARY KEY (session_id, video_frame_index)
            );
        """)
        existing_columns = {row[1] for row in self.db.execute("PRAGMA table_info(fsr_samples)")}
        for column, definition in (("thumb_pressure", "REAL"), ("index_pressure", "REAL"),
                                   ("quality", "TEXT NOT NULL DEFAULT 'uncalibrated'")):
            if column not in existing_columns:
                self.db.execute(f"ALTER TABLE fsr_samples ADD COLUMN {column} {definition}")
        self.session_id = next_id
        self.db.execute("INSERT INTO sessions(id, started_utc, metadata_json) VALUES (?, ?, ?)",
                        (next_id, metadata["recording_start_wall_time_utc"], json.dumps(metadata)))
        self.db.commit()
        self.last_commit = time.monotonic()
        self.frame_count = 0
        self.fsr_sample_count = 0
        self.video_frame_count = 0
        self.video_origin_ms = None
        self.last_video_frame = None
        self.last_video_frame_id = 0
        self.dropped_video_frames = 0
        self.video_error = None
        video = metadata.get("actual_camera_resolution", {})
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        if width > 0 and height > 0:
            import cv2
            fps = float(video.get("fps_property") or 30.0)
            if not 1 <= fps <= 120:
                fps = 30.0
            self.video_fps = fps
            writer = cv2.VideoWriter(str(self.session_dir / "camera.mp4"),
                                     cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            if writer.isOpened():
                self.video_writer = writer
                self.video_index_file = (self.session_dir / "video_frames.jsonl").open("w", encoding="utf-8")
                self.video_queue = queue.Queue(maxsize=60)
                self.video_thread = threading.Thread(target=self._encode_video, daemon=True)
                self.video_thread.start()
            else:
                writer.release()
                metadata["video_error"] = "OpenCV could not open MP4 writer"
                self.update_metadata({"video_error": metadata["video_error"]})
        return self.session_dir

    def _encode_video(self) -> None:
        assert self.video_queue is not None and self.video_writer is not None
        try:
            while True:
                frame = self.video_queue.get()
                if frame is None:
                    break
                self.video_writer.write(frame)
        except Exception as error:
            self.video_error = str(error)
        finally:
            self.video_writer.release()

    def _commit_periodically(self) -> None:
        if self.db and time.monotonic() - self.last_commit >= 0.5:
            self.db.commit()
            self.last_commit = time.monotonic()

    def write_frame(self, frame_record: dict[str, Any]) -> None:
        if not self.is_recording:
            return
        serializable = {
            key: value for key, value in frame_record.items()
            if not key.startswith("_")
        }
        for hand in serializable.get("hands", []):
            hand.pop("_mp_landmarks", None)
        self.data_file.write(json.dumps(serializable, separators=(",", ":")) + "\n")
        if self.db:
            self.db.execute("INSERT INTO frames(session_id, frame_id, session_time_ms, hands_json, pose_json, grasp_state) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (self.session_id, serializable["frame_id"],
                             serializable.get("session_time_ms", serializable.get("timestamp_ms", 0)),
                             json.dumps(serializable.get("hands", []), separators=(",", ":")),
                             json.dumps(serializable.get("pose", {}), separators=(",", ":")),
                             serializable.get("grasp_state")))
            self._commit_periodically()
        self.frame_count += 1

    def write_robot_frame(self, record):
        if self.robot_file:
            self.robot_file.write(json.dumps(record, separators=(",", ":")) + "\n")
            if self.db:
                self.db.execute("UPDATE frames SET robot_json=? WHERE session_id=? AND frame_id=?",
                                (json.dumps({"hands": record.get("hands", []),
                                             "arms": record.get("arms", [])}, separators=(",", ":")),
                                 self.session_id, record["frame_id"]))

    def write_fsr_samples(self, samples: list[dict]) -> None:
        if not self.fsr_file or not samples:
            return
        self.fsr_sample_count += len(samples)
        self.fsr_file.writelines(json.dumps(sample, separators=(",", ":")) + "\n" for sample in samples)
        if self.db:
            self.db.executemany("INSERT INTO fsr_samples(session_id, session_time_ms, esp_timestamp_us, fsr1_raw, fsr2_raw, "
                                "thumb_pressure, index_pressure, quality) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                ((self.session_id, sample["session_time_ms"], sample["esp_timestamp_us"],
                                  sample["fsr1_raw"], sample["fsr2_raw"], sample.get("thumb_pressure"),
                                  sample.get("index_pressure"), sample.get("quality", "uncalibrated"))
                                 for sample in samples))
            self._commit_periodically()

    def write_video_frame(self, frame, frame_id: int, session_time_ms: float) -> None:
        if not self.video_queue or not self.video_index_file or self.video_error:
            return
        if self.video_origin_ms is None:
            self.video_origin_ms = session_time_ms
        target_index = max(self.video_frame_count,
                           round((session_time_ms - self.video_origin_ms) * self.video_fps / 1000))
        # OpenCV writes fixed-rate MP4. Repeat the previous image in missing
        # time slots so video playback follows the monotonic capture clock.
        while self.last_video_frame is not None and self.video_frame_count < target_index:
            slot_ms = self.video_origin_ms + self.video_frame_count * 1000 / self.video_fps
            if not self._queue_video_frame(self.last_video_frame, self.last_video_frame_id,
                                           slot_ms, duplicate=True):
                break
        current = frame.copy()
        if self._queue_video_frame(current, frame_id, session_time_ms):
            self.last_video_frame = current
            self.last_video_frame_id = frame_id

    def _queue_video_frame(self, frame, frame_id: int, session_time_ms: float,
                           duplicate: bool = False) -> bool:
        assert self.video_queue is not None and self.video_index_file is not None
        try:
            self.video_queue.put_nowait(frame)
        except queue.Full:
            self.dropped_video_frames += 1
            return False
        row = {"video_frame_index": self.video_frame_count, "frame_id": frame_id,
               "session_time_ms": round(session_time_ms, 3), "duplicate": duplicate}
        self.video_index_file.write(json.dumps(row, separators=(",", ":")) + "\n")
        if self.db:
            self.db.execute("INSERT INTO video_frames(session_id, video_frame_index, frame_id, session_time_ms) "
                            "VALUES (?, ?, ?, ?)",
                            (self.session_id, self.video_frame_count, frame_id, session_time_ms))
        self.video_frame_count += 1
        return True

    def write_event(self, session_time_ms: float, event: str, source: str = "vision+fsr") -> None:
        if not self.events_file:
            return
        row = {"session_time_ms": session_time_ms, "event": event, "source": source}
        self.events_file.write(json.dumps(row, separators=(",", ":")) + "\n")
        if self.db:
            self.db.execute("INSERT INTO events(session_id, session_time_ms, event, source) VALUES (?, ?, ?, ?)",
                            (self.session_id, session_time_ms, event, source))
            self._commit_periodically()

    def update_metadata(self, updates: dict[str, Any]) -> None:
        if not self.session_dir:
            return
        metadata_path = self.session_dir / "metadata.json"
        if not metadata_path.exists():
            return
        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        metadata.update(updates)
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        if "calibration" in updates:
            with (self.session_dir / "calibration.json").open("w", encoding="utf-8") as f:
                json.dump(updates["calibration"], f, indent=2)
        if self.db:
            self.db.execute("UPDATE sessions SET metadata_json=?, frame_count=? WHERE id=?",
                            (json.dumps(metadata), self.frame_count, self.session_id))
            self.db.commit()

    def stop(self) -> None:
        if not self.is_recording and self.db is None:
            return
        if self.video_queue and self.video_thread:
            if self.video_thread.is_alive():
                self.video_queue.put(None)
            self.video_thread.join()
            self.video_queue = None
            self.video_thread = None
            self.video_writer = None
        self.update_metadata({"recorded_fsr_samples": self.fsr_sample_count,
                              "recorded_video_frames": self.video_frame_count,
                              "dropped_video_frames": self.dropped_video_frames,
                              "video_error": self.video_error})
        if self.db:
            self.db.execute("UPDATE sessions SET frame_count=? WHERE id=?", (self.frame_count, self.session_id))
            self.db.commit()
            self.db.close()
        self.db = None
        for handle in (self.fsr_file, self.events_file, self.video_index_file):
            if handle:
                handle.flush()
                handle.close()
        self.fsr_file = None
        self.events_file = None
        self.video_index_file = None
        if self.robot_file:
            self.robot_file.flush()
            self.robot_file.close()
        self.robot_file = None
        if self.data_file:
            self.data_file.flush()
            self.data_file.close()
        self.data_file = None
