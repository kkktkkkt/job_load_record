import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "activity.db"

VALID_CATEGORIES = ("focus", "distraction", "meeting", "neutral")


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

        # app_categories テーブルを作成 or マイグレーション
        # 旧テーブルに 'meeting' が入れられない CHECK 制約がある場合は再作成
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_categories (
                app_name TEXT PRIMARY KEY,
                category TEXT NOT NULL
            )
        """)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO app_categories (app_name, category) VALUES ('__probe__', 'meeting')"
            )
            conn.execute("DELETE FROM app_categories WHERE app_name = '__probe__'")
        except sqlite3.IntegrityError:
            # 旧 CHECK 制約あり → テーブルを再作成してデータを移行
            conn.execute("ALTER TABLE app_categories RENAME TO _app_categories_old")
            conn.execute("""
                CREATE TABLE app_categories (
                    app_name TEXT PRIMARY KEY,
                    category TEXT NOT NULL
                )
            """)
            conn.execute("INSERT INTO app_categories SELECT * FROM _app_categories_old")
            conn.execute("DROP TABLE _app_categories_old")

        conn.commit()


def insert_activity(timestamp: datetime, app_name: str, window_title: str, duration_seconds: float):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO activity (timestamp, app_name, window_title, duration_seconds) VALUES (?, ?, ?, ?)",
            (timestamp.isoformat(timespec="seconds"), app_name, window_title, round(duration_seconds, 1))
        )
        conn.commit()


def get_categories() -> dict[str, str]:
    """app_name -> category の辞書を返す"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT app_name, category FROM app_categories").fetchall()
    return {row[0]: row[1] for row in rows}


def set_category(app_name: str, category: str):
    """カテゴリを登録・更新する。'neutral' なら削除。"""
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    with sqlite3.connect(DB_PATH) as conn:
        if category == "neutral":
            conn.execute("DELETE FROM app_categories WHERE app_name = ?", (app_name,))
        else:
            conn.execute(
                "INSERT INTO app_categories (app_name, category) VALUES (?, ?) "
                "ON CONFLICT(app_name) DO UPDATE SET category = excluded.category",
                (app_name, category)
            )
        conn.commit()
