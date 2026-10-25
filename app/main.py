from __future__ import annotations

import argparse
import copy
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2

from app.camera import add_camera_args, choose_camera_index, enumerate_cameras, open_camera
from app.hand_tracker import HandTracker
from app.fsr_reader import FSRReader
from app.grasp_fusion import GraspFusion
from app.recorder import SessionRecorder
from app.retarget import Retargeter


def put_text(frame, text: str, x: int, y: int, scale: float = 0.62, color=(255, 255, 255), thickness: int = 2) -> None:
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_status_panel(frame, camera_label: str, measured_fps: float, hands: list[dict], recording: bool) -> None:
    status = "REC: RECORDING" if recording else "READY"
    status_color = (0, 0, 255) if recording else (80, 255, 80)
    put_text(frame, f"CAMERA: {camera_label}", 12, 28)
    put_text(frame, f"FPS: {measured_fps:05.1f}", 12, 56)
    put_text(frame, f"HANDS: {len(hands)}", 12, 84)
    put_text(frame, status, 12, 112, color=status_color)
    if not hands:
        put_text(frame, "HAND NOT DETECTED", 12, 146, color=(0, 220, 255))


def draw_hand_metrics(frame, hands: list[dict]) -> None:
    height, width = frame.shape[:2]
    x = max(12, width - 300)
    y = 28
    for hand in hands:
        confidence = hand["confidence"]
        title = hand["handedness"].upper()
        if confidence is not None:
            title += f" {confidence:.2f}"
        put_text(frame, title, x, y, color=(0, 255, 255))
        y += 26
        for name in ("thumb", "index", "middle", "ring", "pinky"):
            put_text(frame, f"{name.title():<7} {hand['curls'][name]:.2f}", x, y, scale=0.55)
            y += 22
        put_text(frame, f"POSE    {hand['grip_pose']}", x, y, scale=0.55, color=(80, 255, 80))
        y += 28
        for label, point in hand["key_points"].items():
            put_text(frame, f"{label:<10} {point['x']:.2f},{point['y']:.2f}", x, y, scale=0.45)
            y += 18
        y += 14
        if y > height - 20:
            break


def clean_hands_for_recording(hands: list[dict]) -> list[dict]:
    cleaned = []
    for hand in hands:
        item = dict(hand)
        cleaned.append(item)
    return cleaned


def mirror_hands_for_display(hands: list[dict]) -> list[dict]:
    mirrored = copy.deepcopy(hands)
    for hand in mirrored:
        for landmark in hand["landmarks"]:
            landmark["x"] = 1.0 - landmark["x"]
        for point in hand["key_points"].values():
            point["x"] = 1.0 - point["x"]
    return mirrored


def main() -> int:
    parser = argparse.ArgumentParser(description="Low-latency MediaPipe hand capture from Camo/iPhone webcam.")
    add_camera_args(parser)
    parser.add_argument("--model", default="models/hand_landmarker.task", help="Path to MediaPipe hand landmarker task model")
    parser.add_argument("--self-test-frames", type=int, default=0, help="Process N frames without opening the preview window")
    parser.add_argument("--record-immediately", action="store_true", help="Start JSONL recording as soon as capture begins")
    parser.add_argument("--web", action="store_true", help="Serve local 3D retargeting workspace")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fsr-port", default="COM7", help="ESP32 serial port for the two FSR channels")
    parser.add_argument("--fsr-transport", choices=("serial", "wifi"), default="serial",
                        help="Receive ESP32 FSR samples over USB serial or local Wi-Fi UDP")
    parser.add_argument("--fsr-wifi-port", type=int, default=8766,
                        help="UDP listening port for Wi-Fi FSR samples (default: 8766)")
    parser.add_argument("--no-fsr", action="store_true", help="Run without an FSR connection")
    args = parser.parse_args()

    camera_infos = enumerate_cameras(args.max_camera_index, args.width, args.height, args.fps, args.camera_backend)
    if args.list_cameras:
        print("Detected camera indices:")
        for info in camera_infos:
            name = f" name_hint={info.name_hint!r}" if info.name_hint else ""
            print(f"  index={info.index} opened={info.opened} actual={info.width}x{info.height} fps_prop={info.fps:.1f}{name}")
        if not camera_infos:
            print("  none")
        names = [info.name_hint for info in camera_infos if info.name_hint]
        if names:
            print("Windows camera name hints:")
            for name in names:
                print(f"  {name}")
        return 0

    camera_index = choose_camera_index(camera_infos, args.camera)
    if camera_index is None:
        print("Could not open any camera device.")
        print("Run with --list-cameras after connecting/enabling Camo, then choose one with --camera N.")
        return 2

    selected_info = next((info for info in camera_infos if info.index == camera_index), None)
    camera_label = args.camera_label or ("CAMO" if selected_info and selected_info.name_hint and "camo" in selected_info.name_hint.lower() else f"INDEX {camera_index}")
    cap = open_camera(camera_index, args.width, args.height, args.fps, args.camera_backend)
    if not cap.isOpened():
        print(f"Could not open camera index {camera_index}.")
        print("Available cameras:")
        for info in camera_infos:
            print(f"  {info.index}: {info.width}x{info.height} fps_prop={info.fps:.1f} {info.name_hint or ''}")
        return 2

    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps_prop = float(cap.get(cv2.CAP_PROP_FPS))
    print(f"Using camera index {camera_index}: requested {args.width}x{args.height}@{args.fps}, actual {actual_width}x{actual_height}, fps_prop {actual_fps_prop:.1f}")

    tracker = HandTracker(model_path=args.model, max_hands=2)
    fsr_reader = None if args.no_fsr else FSRReader(args.fsr_port, transport=args.fsr_transport,
                                                    wifi_port=args.fsr_wifi_port)
    if fsr_reader:
        fsr_reader.start()
    recorder = SessionRecorder()
    session_start_ns = time.perf_counter_ns()
    wall_start = datetime.now(timezone.utc).isoformat()
    frame_id = 0
    measured_fps = 0.0
    fps_count = 0
    fps_window_start = time.perf_counter()
    last_session_dir: Path | None = None
    max_hands_seen = 0
    retargeter = Retargeter()
    fusion = GraspFusion()
    live = None
    if args.web:
        from app.live_server import LiveServer
        live = LiveServer(args.port)
        live.start()
        print(f"Live robot workspace: http://localhost:{args.port}", flush=True)

    metadata_base = {
        "requested_camera_resolution": {"width": args.width, "height": args.height, "fps": args.fps},
        "actual_camera_resolution": {"width": actual_width, "height": actual_height, "fps_property": actual_fps_prop},
        "measured_fps": None,
        "mediapipe": {"hands": tracker.model_info},
        "session_start_time_utc": wall_start,
        "timestamp_clock": "time.perf_counter_ns, milliseconds since application start",
        "sensor_timing": "ESP32 timestamp retained; session_time_ms uses PC monotonic receive time",
        "fsr": {"transport": args.fsr_transport if fsr_reader else None,
                "port": args.fsr_port if fsr_reader and args.fsr_transport == "serial" else None,
                "baud": 115200 if fsr_reader and args.fsr_transport == "serial" else None,
                "udp_port": args.fsr_wifi_port if fsr_reader and args.fsr_transport == "wifi" else None,
                "sample_rate_target_hz": 100, "fsr1_pin": 34, "fsr2_pin": 35,
                "pressure_units": "relative, not newtons", "tof": "disabled"},
        "camera_index": camera_index,
        "camera_backend": args.camera_backend,
        "camera_identifier": selected_info.name_hint if selected_info else None,
        "retargeting": {"version": 2, "units": "visual workspace units, not meters",
                        "ema_alpha": 0.82, "orientation": "column-major 3x3 rotation matrix",
                        "preview_mirrored": True},
    }
    if args.record_immediately:
        last_session_dir = recorder.start(dict(metadata_base,
                                               calibration=fsr_reader.calibration_snapshot() if fsr_reader else None))
        print(f"Recording to {last_session_dir}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                put_text(frame, "CAMERA FRAME READ FAILED", 12, 28, color=(0, 0, 255)) if frame is not None else None
                time.sleep(0.01)
                continue

            frame_id += 1
            timestamp_ms = (time.perf_counter_ns() - session_start_ns) / 1_000_000
            hands = tracker.detect(frame, int(timestamp_ms))
            robot_hands = retargeter.update(hands, actual_width / actual_height, int(timestamp_ms))
            fsr = fsr_reader.snapshot() if fsr_reader else {"status": "DISABLED", "channels": []}
            raw_fsr_samples = fsr_reader.drain_samples() if fsr_reader else []
            grasp_state, grasp_event = fusion.update(timestamp_ms, hands, fsr)
            max_hands_seen = max(max_hands_seen, len(hands))

            preview = cv2.flip(frame, 1)
            display_hands = mirror_hands_for_display(hands)
            tracker.draw(preview, display_hands)

            fps_count += 1
            now = time.perf_counter()
            elapsed = now - fps_window_start
            if elapsed >= 0.5:
                measured_fps = fps_count / elapsed
                fps_count = 0
                fps_window_start = now

            draw_status_panel(preview, camera_label, measured_fps, display_hands, recorder.is_recording)
            draw_hand_metrics(preview, display_hands)

            frame_record = {
                "timestamp_ms": int(timestamp_ms),
                "session_time_ms": round(timestamp_ms, 3),
                "frame_id": frame_id,
                "hands": clean_hands_for_recording(hands),
                "fsr": fsr,
                "grasp_state": grasp_state,
            }
            if recorder.is_recording:
                calibration = fsr_reader.calibration_snapshot() if fsr_reader else {"status": "missing"}
                can_normalize = calibration["status"] == "available" and fsr.get("status") == "LIVE"
                quality = "valid" if can_normalize else (
                    "check_signal" if fsr.get("status") == "CHECK SIGNAL" else "uncalibrated")
                samples_to_save = []
                for sample in raw_fsr_samples:
                    if sample["pc_received_ns"] < session_start_ns:
                        continue
                    row = {"session_time_ms": round((sample["pc_received_ns"] - session_start_ns) / 1_000_000, 3),
                           "esp_timestamp_us": sample["esp_timestamp_us"],
                           "fsr1_raw": sample["fsr1_raw"], "fsr2_raw": sample["fsr2_raw"],
                           "quality": quality, "thumb_pressure": None, "index_pressure": None}
                    if can_normalize:
                        for index, key in ((0, "thumb_pressure"), (1, "index_pressure")):
                            raw = sample["fsr1_raw"] if index == 0 else sample["fsr2_raw"]
                            baseline = calibration["baseline"][index]
                            pressed = calibration["pressed"][index]
                            row[key] = round(max(0.0, min(1.0, (baseline - raw) / (baseline - pressed))), 4)
                    samples_to_save.append(row)
                recorder.write_fsr_samples(samples_to_save)
                recorder.write_frame(frame_record)
                recorder.write_robot_frame({"timestamp_ms": int(timestamp_ms), "frame_id": frame_id,
                                            "hands": robot_hands, "arms": [], "fsr": fsr})
                recorder.write_video_frame(frame, frame_id, round(timestamp_ms, 3))
                if grasp_event:
                    recorder.write_event(round(timestamp_ms, 3), grasp_event)

            commands = live.take_commands() if live else []
            for command in commands:
                if command == "start":
                    last_session_dir = recorder.start(dict(
                        metadata_base, measured_fps=measured_fps,
                        calibration=fsr_reader.calibration_snapshot() if fsr_reader else None))
                elif command == "stop":
                    recorder.update_metadata({"measured_fps": measured_fps, "recorded_frames": recorder.frame_count})
                    recorder.stop()
                elif command == "calibrate-fsr" and fsr_reader:
                    if fsr_reader.calibrate() and recorder.is_recording:
                        recorder.update_metadata({"calibration": fsr_reader.calibration_snapshot()})
                elif command == "calibrate-fsr-pressed" and fsr_reader:
                    if fsr_reader.calibrate_pressed() and recorder.is_recording:
                        recorder.update_metadata({"calibration": fsr_reader.calibration_snapshot()})
            if live:
                ok_jpeg, jpeg = cv2.imencode(".jpg", cv2.resize(preview, (640, 360)), [cv2.IMWRITE_JPEG_QUALITY, 75])
                live.publish(dict(frame_record, robot_hands=robot_hands, robot_arms=[],
                                  fps=measured_fps,
                                  captured_unix_ms=time.time() * 1000,
                                  status="TRACKING" if hands else "TRACKING LOST",
                                  camera=camera_label, recording=recorder.is_recording,
                                  session=str(recorder.session_dir) if recorder.session_dir else None),
                             jpeg.tobytes() if ok_jpeg else b"")

            if args.self_test_frames and frame_id >= args.self_test_frames:
                break

            cv2.imshow("Camo MediaPipe Hand Capture", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                metadata = dict(metadata_base)
                metadata["measured_fps"] = measured_fps
                metadata["calibration"] = fsr_reader.calibration_snapshot() if fsr_reader else None
                last_session_dir = recorder.start(metadata)
                print(f"Recording to {last_session_dir}")
            if key in (ord("s"), ord("S")):
                recorder.update_metadata({"measured_fps": measured_fps, "recorded_frames": recorder.frame_count})
                recorder.stop()
                if last_session_dir:
                    print(f"Stopped recording. Data saved under {last_session_dir}")
    finally:
        recorder.update_metadata({"measured_fps": measured_fps, "recorded_frames": recorder.frame_count})
        recorder.stop()
        tracker.close()
        if fsr_reader:
            fsr_reader.close()
        cap.release()
        cv2.destroyAllWindows()
        if live:
            live.close()

    if last_session_dir:
        print(f"Last recording directory: {last_session_dir}")
    if args.self_test_frames:
        print(
            "Self-test complete: "
            f"frames={frame_id}, measured_fps={measured_fps:.1f}, max_hands_seen={max_hands_seen}, "
            f"actual_resolution={actual_width}x{actual_height}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
