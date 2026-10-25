from __future__ import annotations

import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from app.hand_geometry import Landmark, calculate_finger_curls, classify_grip_pose, key_point_summary


DEFAULT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


class HandTracker:
    def __init__(
        self,
        model_path: str | Path = "models/hand_landmarker.task",
        max_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self.model_path = Path(model_path)
        ensure_model(self.model_path)

        base_options = python.BaseOptions(model_asset_path=str(self.model_path))
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)
        self.hand_connections = vision.HandLandmarksConnections.HAND_CONNECTIONS

    @property
    def model_info(self) -> dict[str, Any]:
        return {
            "api": "mediapipe.tasks.python.vision.HandLandmarker",
            "model_path": str(self.model_path),
            "model_source": DEFAULT_MODEL_URL,
            "mediapipe_version": getattr(mp, "__version__", "unknown"),
        }

    def close(self) -> None:
        self.landmarker.close()

    def detect(self, bgr_frame, timestamp_ms: int) -> list[dict[str, Any]]:
        rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        hands: list[dict[str, Any]] = []
        for hand_index, normalized_landmarks in enumerate(result.hand_landmarks):
            handedness_category = result.handedness[hand_index][0] if result.handedness else None
            landmarks = [
                Landmark(id=i, x=lm.x, y=lm.y, z=lm.z)
                for i, lm in enumerate(normalized_landmarks)
            ]
            curls = calculate_finger_curls(landmarks)
            hands.append(
                {
                    "handedness": handedness_category.category_name if handedness_category else "Unknown",
                    "confidence": handedness_category.score if handedness_category else None,
                    "landmarks": [asdict(item) for item in landmarks],
                    "curls": curls,
                    "grip_pose": classify_grip_pose(curls),
                    "key_points": key_point_summary(landmarks),
                }
            )
        return hands

    def draw(self, frame, hands: list[dict[str, Any]]) -> None:
        height, width = frame.shape[:2]
        for hand in hands:
            points = [
                (int(lm["x"] * width), int(lm["y"] * height))
                for lm in hand["landmarks"]
            ]
            for connection in self.hand_connections:
                start = points[connection.start]
                end = points[connection.end]
                cv2.line(frame, start, end, (40, 220, 255), 3, cv2.LINE_AA)
                cv2.line(frame, start, end, (0, 70, 90), 1, cv2.LINE_AA)
            for point in points:
                cv2.circle(frame, point, 6, (0, 0, 0), -1, cv2.LINE_AA)
                cv2.circle(frame, point, 4, (80, 255, 80), -1, cv2.LINE_AA)
            wrist = hand["landmarks"][0]
            label = hand["handedness"].upper()
            if hand["confidence"] is not None:
                label = f"{label} {hand['confidence']:.2f}"
            x = int(wrist["x"] * width)
            y = max(24, int(wrist["y"] * height) - 12)
            cv2.putText(frame, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)


def ensure_model(model_path: Path) -> None:
    if model_path.exists():
        return
    model_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(DEFAULT_MODEL_URL, model_path)
