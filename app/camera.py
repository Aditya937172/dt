from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from typing import Iterable

import cv2


@dataclass
class CameraInfo:
    index: int
    opened: bool
    width: int = 0
    height: int = 0
    fps: float = 0.0
    name_hint: str | None = None


def _capture_backend(name: str = "dshow") -> int:
    if name == "msmf":
        return cv2.CAP_MSMF
    return cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY


def get_windows_camera_names() -> list[str]:
    """Return Windows camera-like device names when PowerShell/CIM is available."""
    command = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPClass -in @('Camera','Image') -or $_.Name -match 'camera|webcam|camo' } | "
        "Select-Object -ExpandProperty Name | ConvertTo-Json"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if isinstance(parsed, str):
        return [parsed]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if item]
    return []


def enumerate_cameras(
    max_index: int = 10,
    requested_width: int = 1280,
    requested_height: int = 720,
    requested_fps: int = 30,
    backend_name: str = "dshow",
) -> list[CameraInfo]:
    infos: list[CameraInfo] = []
    backend = _capture_backend(backend_name)

    for index in range(max_index + 1):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)
            cap.set(cv2.CAP_PROP_FPS, requested_fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, _ = cap.read()
            info = CameraInfo(
                index=index,
                opened=bool(ok),
                width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps=float(cap.get(cv2.CAP_PROP_FPS)),
                # PnP enumeration order does not match OpenCV camera indices on Windows.
                name_hint=None,
            )
            infos.append(info)
        cap.release()

    return infos


def choose_camera_index(infos: Iterable[CameraInfo], requested_index: int | None = None) -> int | None:
    if requested_index is not None:
        return requested_index

    info_list = list(infos)
    for info in info_list:
        if info.name_hint and "camo" in info.name_hint.lower():
            return info.index

    return info_list[0].index if info_list else None


def open_camera(index: int, width: int, height: int, fps: int, backend_name: str = "dshow") -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, _capture_backend(backend_name))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def add_camera_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--camera", type=int, default=None, help="Camera index to use, e.g. --camera 1")
    parser.add_argument("--camera-backend", choices=("dshow", "msmf"), default="dshow")
    parser.add_argument("--camera-label", default=None, help="Optional display name for the selected camera")
    parser.add_argument("--list-cameras", action="store_true", help="List detected camera indices and exit")
    parser.add_argument("--width", type=int, default=1280, help="Requested capture width")
    parser.add_argument("--height", type=int, default=720, help="Requested capture height")
    parser.add_argument("--fps", type=int, default=30, help="Requested capture FPS")
    parser.add_argument("--max-camera-index", type=int, default=10, help="Highest camera index to probe")
