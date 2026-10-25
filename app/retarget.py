"""Visual workspace coordinates, not metric robot kinematics."""
import numpy as np

FINGERS = {"thumb": [1, 2, 3, 4], "index": [5, 6, 7, 8],
           "middle": [9, 10, 11, 12], "ring": [13, 14, 15, 16], "pinky": [17, 18, 19, 20]}


class Retargeter:
    def __init__(self, alpha=0.82):
        self.alpha = alpha
        self.previous = {}

    def update(self, hands, aspect, timestamp_ms):
        states = []
        active = set()
        for hand in hands:
            label = hand["handedness"]
            key = label + str(sum(s["hand"] == label for s in states))
            active.add(key)
            raw = np.array([[p["x"], p["y"], p["z"]] for p in hand["landmarks"]])
            wrist = raw[0]
            span = max(np.linalg.norm((raw[5] - raw[17]) * [aspect, 1, .65]),
                       .65 * np.linalg.norm((raw[9] - raw[0]) * [aspect, 1, .65]), .015)
            # Map every image landmark into one shared scene plane. This preserves
            # apparent hand size and relative placement as a hand moves in frame.
            height = 6.0
            points = np.column_stack(((0.5 - raw[:, 0]) * height * aspect,
                                      (0.5 - raw[:, 1]) * height,
                                      np.clip(-raw[:, 2] * height * 0.65
                                              + (span - 0.16) * 2, -1.8, 1.8)))
            if key in self.previous:
                points = self.alpha * points + (1 - self.alpha) * self.previous[key][0]
            up = points[9] - points[0]
            right = points[5] - points[17]
            up /= max(np.linalg.norm(up), 1e-6)
            right -= up * np.dot(right, up)
            norm = np.linalg.norm(right)
            if norm < 1e-4:
                basis = self.previous[key][1] if key in self.previous else np.eye(3)
            else:
                right /= norm
                basis = np.column_stack((right, up, np.cross(right, up)))
            # Smooth the rotation basis and project it back onto SO(3).
            if key in self.previous:
                u, _, vt = np.linalg.svd(self.alpha * basis + (1 - self.alpha) * self.previous[key][1])
                basis = u @ np.diag([1, 1, np.linalg.det(u @ vt)]) @ vt
            self.previous[key] = (points, basis)
            states.append({"timestamp_ms": timestamp_ms, "hand": label,
                           "grip_pose": hand.get("grip_pose", "UNKNOWN"), "track_id": key,
                           "image_wrist": [float(wrist[0]), float(wrist[1])],
                           "wrist_position": points[0].tolist(),
                           "palm_position": points[[0, 5, 9, 13, 17]].mean(axis=0).tolist(),
                           "palm_orientation": basis.T.reshape(-1).tolist(),
                           "palm_width": float(np.linalg.norm(points[5] - points[17])),
                           "palm_length": float(np.linalg.norm(points[9] - points[0])),
                           "landmarks": points.tolist(),
                           "joints": {name: points[ids].tolist() for name, ids in FINGERS.items()}})
        self.previous = {key: value for key, value in self.previous.items() if key in active}
        return states

