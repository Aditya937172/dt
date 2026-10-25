"""Bring an existing local captures.sqlite file to the current FSR schema."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> None:
    path = Path("sessions/captures.sqlite")
    if not path.exists():
        print("No capture database exists yet")
        return
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(fsr_samples)")}
        for name, definition in (("thumb_pressure", "REAL"),
                                 ("index_pressure", "REAL"),
                                 ("quality", "TEXT NOT NULL DEFAULT 'uncalibrated'")):
            if name not in columns:
                db.execute(f"ALTER TABLE fsr_samples ADD COLUMN {name} {definition}")
        print("FSR columns:", ", ".join(row[1] for row in db.execute("PRAGMA table_info(fsr_samples)")))


if __name__ == "__main__":
    main()
