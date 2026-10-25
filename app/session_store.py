"""Read recorded sessions from the local SQLite capture index."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path


def list_sessions(root: str | Path = "sessions") -> list[dict]:
    path = Path(root) / "captures.sqlite"
    if not path.exists():
        return []
    with closing(sqlite3.connect(path, timeout=2)) as db:
        rows = db.execute("""
            SELECT s.id, s.started_utc, s.frame_count,
                   MIN(f.session_time_ms), MAX(f.session_time_ms),
                   (SELECT COUNT(*) FROM fsr_samples x WHERE x.session_id=s.id),
                   s.metadata_json
            FROM sessions s LEFT JOIN frames f ON f.session_id=s.id
            GROUP BY s.id ORDER BY s.id DESC
        """).fetchall()
    return [{"id": row[0], "started_utc": row[1], "frame_count": row[2],
             "start_ms": row[3], "end_ms": row[4], "fsr_count": row[5],
             "purpose": json.loads(row[6]).get("capture_purpose"),
             "has_video": (Path(root) / f"session_{row[0]:03d}" / "camera.mp4").exists()}
            for row in rows]


def replay_window(session_id: int, start_ms: float, duration_ms: float = 20000,
                  root: str | Path = "sessions") -> dict | None:
    path = Path(root) / "captures.sqlite"
    if not path.exists():
        return None
    duration_ms = max(1000, min(duration_ms, 30000))
    with closing(sqlite3.connect(path, timeout=2)) as db:
        exists = db.execute("SELECT metadata_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not exists:
            return None
        fsr_columns = {row[1] for row in db.execute("PRAGMA table_info(fsr_samples)")}
        pressure_columns = ("thumb_pressure, index_pressure, quality" if "thumb_pressure" in fsr_columns
                            else "NULL, NULL, 'uncalibrated'")
        frames = db.execute("""
            SELECT frame_id, session_time_ms, hands_json, pose_json, robot_json, grasp_state
            FROM frames WHERE session_id=? AND session_time_ms BETWEEN ? AND ?
            ORDER BY session_time_ms LIMIT 1200
        """, (session_id, start_ms, start_ms + duration_ms)).fetchall()
        fsr_rows = db.execute(f"""
            SELECT session_time_ms, fsr1_raw, fsr2_raw, {pressure_columns}
            FROM fsr_samples
            WHERE session_id=? AND session_time_ms BETWEEN ? AND ?
            ORDER BY session_time_ms LIMIT 3500
        """, (session_id, start_ms, start_ms + duration_ms)).fetchall()
        events = db.execute("""
            SELECT session_time_ms, event FROM events
            WHERE session_id=? AND session_time_ms BETWEEN ? AND ?
            ORDER BY session_time_ms
        """, (session_id, start_ms, start_ms + duration_ms)).fetchall()
        video_rows = db.execute("""
            SELECT video_frame_index, session_time_ms FROM video_frames
            WHERE session_id=? AND session_time_ms BETWEEN ? AND ?
            ORDER BY video_frame_index LIMIT 1200
        """, (session_id, start_ms, start_ms + duration_ms)).fetchall()
        video_start = db.execute("SELECT MIN(session_time_ms) FROM video_frames WHERE session_id=?",
                                 (session_id,)).fetchone()[0]
    return {
        "frames": [{"frame_id": row[0], "session_time_ms": row[1],
                    "hands": json.loads(row[2]), "pose": json.loads(row[3]),
                    "robot_hands": json.loads(row[4]).get("hands", []) if row[4] else [],
                    "robot_arms": json.loads(row[4]).get("arms", []) if row[4] else [],
                    "grasp_state": row[5]}
                   for row in frames],
        "fsr": [{"session_time_ms": row[0], "fsr1_raw": row[1], "fsr2_raw": row[2],
                 "thumb_pressure": row[3], "index_pressure": row[4], "quality": row[5]}
                for row in (fsr_rows if len(fsr_rows) < 100 else fsr_rows[::2])],
        "events": [{"session_time_ms": row[0], "event": row[1]} for row in events],
        "video_start_ms": video_start,
        "video_frames": [{"video_frame_index": row[0], "session_time_ms": row[1]}
                         for row in video_rows],
        "video_fps": json.loads(exists[0]).get("actual_camera_resolution", {}).get("fps_property") or 30,
        "calibration": json.loads(exists[0]).get("calibration"),
    }
