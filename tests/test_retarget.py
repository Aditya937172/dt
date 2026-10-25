import copy
import json
import tempfile
import unittest

import numpy as np

from app.retarget import Retargeter
from app.recorder import SessionRecorder


def fixture():
    # Synthetic geometry tests only; these are not physical gesture verification.
    coords = [(0.5, .7, 0)]
    for x in [.35, .42, .5, .58, .66]:
        coords.extend((x, .5 - i * .06, -.01 * i) for i in range(4))
    return {"handedness": "Right", "landmarks": [
        {"id": i, "x": x, "y": y, "z": z} for i, (x, y, z) in enumerate(coords)]}


class RetargetTests(unittest.TestCase):
    def test_independent_index(self):
        hand = fixture()
        original = Retargeter(alpha=1).update([hand], 16/9, 0)[0]
        changed = copy.deepcopy(hand)
        changed["landmarks"][7]["y"] += .05
        bent = Retargeter(alpha=1).update([changed], 16/9, 1)[0]
        self.assertFalse(np.allclose(original["joints"]["index"], bent["joints"]["index"]))
        for finger in ["thumb", "middle", "ring", "pinky"]:
            np.testing.assert_allclose(original["joints"][finger], bent["joints"][finger])

    def test_translation_rotation_loss_depth(self):
        hand = fixture()
        tracker = Retargeter(alpha=1)
        first = tracker.update([hand], 16/9, 0)[0]
        for p in hand["landmarks"]:
            p["x"] += .1
            p["y"] += .1
            p["z"] += 100
        moved = tracker.update([hand], 16/9, 1)[0]
        self.assertLess(moved["wrist_position"][0], first["wrist_position"][0])
        self.assertLess(moved["wrist_position"][1], first["wrist_position"][1])
        rotation = np.array(moved["palm_orientation"]).reshape(3, 3).T
        np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
        self.assertAlmostEqual(np.linalg.det(rotation), 1)
        for p in hand["landmarks"]:
            p["z"] = 0
        hand["landmarks"][5]["z"] = -.2
        rotated = tracker.update([hand], 16/9, 2)[0]
        self.assertFalse(np.allclose(rotated["palm_orientation"], moved["palm_orientation"]))
        self.assertTrue(np.isfinite(rotated["landmarks"]).all())
        self.assertEqual(tracker.update([], 16/9, 3), [])
        self.assertEqual(tracker.previous, {})
        self.assertEqual(len(tracker.update([hand], 16/9, 4)[0]["landmarks"]), 21)

    def test_degenerate_geometry_and_smoothing(self):
        hand = fixture()
        tracker = Retargeter()
        first = tracker.update([hand], 16/9, 0)[0]
        for p in hand["landmarks"]:
            p["x"] += .1
        second = tracker.update([hand], 16/9, 1)[0]
        self.assertAlmostEqual(second["wrist_position"][0] - first["wrist_position"][0],
                               -(16/9) * 6 * .1 * .82)
        for p in hand["landmarks"]:
            p.update(x=.5, y=.5, z=0)
        self.assertTrue(np.isfinite(tracker.update([hand], 16/9, 2)[0]["palm_orientation"]).all())

    def test_image_placement_and_apparent_hand_size(self):
        hand = fixture()
        first = Retargeter(alpha=1).update([hand], 16/9, 0)[0]
        moved = copy.deepcopy(hand)
        for landmark in moved["landmarks"]:
            landmark["x"] += .1
            landmark["y"] += .1
        second = Retargeter(alpha=1).update([moved], 16/9, 1)[0]
        self.assertAlmostEqual(second["wrist_position"][0] - first["wrist_position"][0],
                               -(16/9) * 6 * .1)
        self.assertAlmostEqual(second["wrist_position"][1] - first["wrist_position"][1], -.6)
        enlarged = copy.deepcopy(hand)
        wrist = enlarged["landmarks"][0]
        for landmark in enlarged["landmarks"][1:]:
            landmark["x"] = wrist["x"] + 1.5 * (landmark["x"] - wrist["x"])
            landmark["y"] = wrist["y"] + 1.5 * (landmark["y"] - wrist["y"])
        large = Retargeter(alpha=1).update([enlarged], 16/9, 2)[0]
        self.assertAlmostEqual(large["palm_width"] / first["palm_width"], 1.5)

    def test_recording_alignment(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = SessionRecorder(root)
            path = recorder.start({})
            recorder.write_frame({"timestamp_ms": 12, "frame_id": 1, "hands": []})
            recorder.write_robot_frame({"timestamp_ms": 12, "frame_id": 1, "hands": []})
            recorder.stop()
            a = json.loads((path / "hand_landmarks.jsonl").read_text())
            b = json.loads((path / "robot_hand_state.jsonl").read_text())
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
