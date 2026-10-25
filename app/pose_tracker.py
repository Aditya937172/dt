"""Upper-body landmarks used to place shoulders and elbows in the workspace."""
from __future__ import annotations

import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


DEFAULT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
ARM_IDS = {
    "Left": {"shoulder": 11, "elbow": 13, "wrist": 15},
    "Right": {"shoulder": 12, "elbow": 14, "wrist": 16},
}


class PoseTracker:
    def __init__(self, model_path: str | Path = "models/pose_landmarker_lite.task") -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(DEFAULT_MODEL_URL, self.model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)

    @property
    def model_info(self) -> dict:
        return {"api": "mediapipe.tasks.python.vision.PoseLandmarker",
                "model_path": str(self.model_path), "model_source": DEFAULT_MODEL_URL,
                "mediapipe_version": getattr(mp, "__version__", "unknown")}

    def detect(self, bgr_frame, timestamp_ms: int) -> dict:
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(image, timestamp_ms)
        if not result.pose_landmarks:
            return {}
        landmarks = result.pose_landmarks[0]
        return {
            side: {
                name: {"x": float(landmarks[index].x),
                       "y": float(landmarks[index].y),
                       "z": float(landmarks[index].z),
                       "visibility": float(landmarks[index].visibility or 0)}
                for name, index in joints.items()
            }
            for side, joints in ARM_IDS.items()
        }

    def draw(self, frame, pose: dict) -> None:
        height, width = frame.shape[:2]
        for side, joints in pose.items():
            color = (255, 190, 90) if side == "Left" else (100, 225, 255)
            for a, b in (("shoulder", "elbow"), ("elbow", "wrist")):
                if min(joints[a]["visibility"], joints[b]["visibility"]) < 0.5:
                    continue
                pa = (int((1 - joints[a]["x"]) * width), int(joints[a]["y"] * height))
                pb = (int((1 - joints[b]["x"]) * width), int(joints[b]["y"] * height))
                cv2.line(frame, pa, pb, color, 3, cv2.LINE_AA)
                cv2.circle(frame, pa, 5, color, -1, cv2.LINE_AA)
                cv2.circle(frame, pb, 5, color, -1, cv2.LINE_AA)

    def close(self) -> None:
        self.landmarker.close()
