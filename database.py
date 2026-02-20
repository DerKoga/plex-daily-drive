import json
import sqlite3
from contextlib import contextmanager

import config


def get_connection():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                track_count INTEGER DEFAULT 0,
                podcast_count INTEGER DEFAULT 0,
                music_count INTEGER DEFAULT 0
            )
        """)
        defaults = {
            "playlist_prefix": "Daily Drive",
            "music_count": "20",
            "podcast_count": "3",
            "music_libraries": "[]",
            "podcast_libraries": "[]",
            "schedule_hour": str(config.SCHEDULE_HOUR),
            "schedule_minute": str(config.SCHEDULE_MINUTE),
            "enabled": "true",
            "keep_days": "7",
            "podcast_recent_only": "true",
            "podcast_unplayed_only": "true",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


def get_setting(key, default=None):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def get_all_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}


def save_setting(key, value):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )


def save_settings(settings_dict):
    with get_db() as conn:
        for key, value in settings_dict.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )


def add_history(name, track_count, podcast_count, music_count):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO playlist_history
               (name, track_count, podcast_count, music_count)
               VALUES (?, ?, ?, ?)""",
            (name, track_count, podcast_count, music_count),
        )


def get_history(limit=50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM playlist_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_list_setting(key):
    raw = get_setting(key, "[]")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
