"""Conservative labels inferred from camera pose and relative FSR pressure."""
from __future__ import annotations


class GraspFusion:
    def __init__(self) -> None:
        self.state = "OPEN"
        self.grasp_since_ms: float | None = None

    def update(self, session_time_ms: float, hands: list[dict], fsr: dict) -> tuple[str, str | None]:
        pose = hands[0].get("grip_pose", "UNKNOWN") if hands else "UNKNOWN"
        if fsr.get("status") != "LIVE" or not fsr.get("calibrated") or len(fsr.get("channels", [])) != 2:
            self.state = "VISION ONLY" if hands else "NO TRACKING"
            self.grasp_since_ms = None
            return self.state, None

        thumb, index = (channel.get("level", 0.0) for channel in fsr["channels"])
        highest = max(thumb, index)
        both = min(thumb, index)
        previous = self.state
        if previous in ("GRASP", "HOLD") and highest < 0.12:
            current = "RELEASE"
            self.grasp_since_ms = None
        elif both >= 0.35 and pose in ("PARTIAL", "CLOSED"):
            if self.grasp_since_ms is None:
                self.grasp_since_ms = session_time_ms
            current = "HOLD" if session_time_ms - self.grasp_since_ms >= 350 else "GRASP"
        elif highest >= 0.22 or (previous == "CONTACT" and highest >= 0.12):
            current = "CONTACT"
            self.grasp_since_ms = None
        else:
            current = "REACH" if pose in ("PARTIAL", "CLOSED") else "OPEN"
            self.grasp_since_ms = None
        self.state = current
        event = current if current != previous and current in ("CONTACT", "GRASP", "HOLD", "RELEASE") else None
        return current, event
