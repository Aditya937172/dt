import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.grasp_fusion import GraspFusion
from app.fsr_reader import FSRReader
from app.recorder import SessionRecorder
from app.session_store import list_sessions, replay_window


class CaptureStoreTests(unittest.TestCase):
    def test_raw_sensor_samples_and_frames_survive_recording(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recorder = SessionRecorder(root)
            session = recorder.start({"calibration": {"baseline": [2000, 4095]}})
            recorder.write_frame({"frame_id": 1, "session_time_ms": 101.5,
                                  "hands": [{"grip_pose": "PARTIAL"}], "pose": {},
                                  "grasp_state": "CONTACT"})
            recorder.write_robot_frame({"frame_id": 1, "hands": [{"track_id": "left"}], "arms": []})
            recorder.write_fsr_samples([
                {"session_time_ms": 100.0, "esp_timestamp_us": 5000,
                 "fsr1_raw": 1800, "fsr2_raw": 4095},
                {"session_time_ms": 110.0, "esp_timestamp_us": 15000,
                 "fsr1_raw": 700, "fsr2_raw": 3500,
                 "thumb_pressure": 0.8, "index_pressure": 0.2, "quality": "valid"},
            ])
            recorder.write_event(110.0, "CONTACT")
            recorder.stop()

            self.assertEqual(len((session / "fsr.jsonl").read_text().splitlines()), 2)
            self.assertEqual(len((session / "events.jsonl").read_text().splitlines()), 1)
            with closing(sqlite3.connect(root / "captures.sqlite")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM fsr_samples").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT thumb_pressure FROM fsr_samples ORDER BY id DESC LIMIT 1")
                                 .fetchone()[0], 0.8)
                self.assertEqual(db.execute("SELECT grasp_state FROM frames").fetchone()[0], "CONTACT")
            self.assertEqual(list_sessions(root)[0]["fsr_count"], 2)
            replay = replay_window(1, 100, 1000, root)
            self.assertEqual(replay["frames"][0]["robot_hands"][0]["track_id"], "left")
            self.assertEqual(replay["fsr"][0]["fsr1_raw"], 1800)
            self.assertEqual(replay["fsr"][1]["thumb_pressure"], 0.8)
            self.assertEqual(replay["events"][0]["event"], "CONTACT")

    def test_sensor_fault_does_not_create_grasp_event(self):
        fusion = GraspFusion()
        hands = [{"grip_pose": "CLOSED"}]
        good = {"status": "LIVE", "calibrated": True,
                "channels": [{"level": 0.6}, {"level": 0.7}]}
        self.assertEqual(fusion.update(100, hands, good), ("GRASP", "GRASP"))
        fault = {"status": "CHECK SIGNAL", "calibrated": True,
                 "channels": [{"level": 1}, {"level": 1}]}
        self.assertEqual(fusion.update(200, hands, fault), ("VISION ONLY", None))

    def test_video_timeline_keeps_elapsed_time_when_camera_frames_are_slow(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as temporary:
            recorder = SessionRecorder(temporary)
            session = recorder.start({"actual_camera_resolution":
                                      {"width": 64, "height": 48, "fps_property": 30}})
            for frame_id, stamp in ((1, 0.0), (2, 100.0)):
                recorder.write_frame({"frame_id": frame_id, "session_time_ms": stamp,
                                      "hands": [], "pose": {}})
                recorder.write_video_frame(np.zeros((48, 64, 3), dtype=np.uint8), frame_id, stamp)
            recorder.stop()
            self.assertTrue((session / "camera.mp4").stat().st_size > 0)
            with closing(sqlite3.connect(Path(temporary) / "captures.sqlite")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM video_frames").fetchone()[0], 4)

    def test_two_point_calibration_rejects_pressed_baseline(self):
        reader = FSRReader("TEST")
        reader.samples.extend([(281, 4095)] * 100)
        self.assertFalse(reader.calibrate())
        reader.samples.clear()
        reader.samples.extend([(2200, 4050)] * 100)
        self.assertTrue(reader.calibrate())
        reader.samples.clear()
        reader.samples.extend([(600, 350)] * 100)
        self.assertTrue(reader.calibrate_pressed())
        self.assertEqual(reader.calibration_snapshot()["pressed"], [600, 350])


if __name__ == "__main__":
    unittest.main()
