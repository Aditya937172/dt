from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Landmark:
    id: int
    x: float
    y: float
    z: float


FINGER_JOINTS = {
    "thumb": (1, 2, 3, 4),
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}

KEY_POINTS = {
    "wrist": 0,
    "thumb tip": 4,
    "index tip": 8,
    "middle tip": 12,
    "ring tip": 16,
    "pinky tip": 20,
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def angle_degrees(a: Landmark, b: Landmark, c: Landmark) -> float:
    ba = (a.x - b.x, a.y - b.y, a.z - b.z)
    bc = (c.x - b.x, c.y - b.y, c.z - b.z)
    dot = ba[0] * bc[0] + ba[1] * bc[1] + ba[2] * bc[2]
    mag_ba = math.sqrt(ba[0] ** 2 + ba[1] ** 2 + ba[2] ** 2)
    mag_bc = math.sqrt(bc[0] ** 2 + bc[1] ** 2 + bc[2] ** 2)
    if mag_ba == 0.0 or mag_bc == 0.0:
        return 180.0
    cosine = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cosine))


def joint_curl_from_angle(angle: float) -> float:
    # Extended fingers are near 170-180 degrees. Curled joints trend toward 55-90.
    return clamp((170.0 - angle) / 110.0)


def calculate_finger_curls(landmarks: Sequence[Landmark]) -> dict[str, float]:
    curls: dict[str, float] = {}
    for finger, joint_ids in FINGER_JOINTS.items():
        mcp, pip, dip, tip = (landmarks[i] for i in joint_ids)
        if finger == "thumb":
            first = joint_curl_from_angle(angle_degrees(landmarks[0], mcp, pip))
            second = joint_curl_from_angle(angle_degrees(mcp, pip, dip))
            third = joint_curl_from_angle(angle_degrees(pip, dip, tip))
            curls[finger] = clamp((first * 0.30) + (second * 0.45) + (third * 0.25))
        else:
            pip_curl = joint_curl_from_angle(angle_degrees(mcp, pip, dip))
            dip_curl = joint_curl_from_angle(angle_degrees(pip, dip, tip))
            curls[finger] = clamp((pip_curl * 0.65) + (dip_curl * 0.35))
    return curls


def classify_grip_pose(curls: dict[str, float]) -> str:
    if not curls:
        return "UNKNOWN"
    average = sum(curls.values()) / len(curls)
    if average < 0.30:
        return "OPEN"
    if average < 0.65:
        return "PARTIAL"
    return "CLOSED"


def key_point_summary(landmarks: Sequence[Landmark]) -> dict[str, dict[str, float]]:
    return {
        label: {"x": landmarks[index].x, "y": landmarks[index].y}
        for label, index in KEY_POINTS.items()
    }
