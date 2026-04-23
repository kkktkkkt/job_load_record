import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "activity.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app_name TEXT NOT NULL,
                window_title TEXT,
                duration_seconds REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON activity(timestamp)")
        conn.commit()


def insert_activity(timestamp: datetime, app_name: str, window_title: str, duration_seconds: float):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO activity (timestamp, app_name, window_title, duration_seconds) VALUES (?, ?, ?, ?)",
            (timestamp.isoformat(timespec="seconds"), app_name, window_title, round(duration_seconds, 1))
        )
        conn.commit()
