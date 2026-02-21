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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS podcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                artist TEXT DEFAULT '',
                feed_url TEXT NOT NULL UNIQUE,
                artwork TEXT DEFAULT '',
                genre TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        defaults = {
            "plex_url": config.PLEX_URL,
            "plex_token": config.PLEX_TOKEN,
            "playlist_prefix": "Daily Drive",
            "music_count": "20",
            "podcast_count": "3",
            "music_libraries": "[]",
            "podcast_libraries": "[]",
            "schedules": '[{"hour": 6, "minute": 0}]',
            "enabled": "true",
            "keep_days": "7",
            "podcast_recent_only": "true",
            "podcast_unplayed_only": "true",
            "podcast_download_path": "/podcasts",
            "podcast_max_episodes": "3",
            "playlist_description": "",
            "discovery_ratio": "40",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        # Migrate: if old schedule_hour/schedule_minute exist, convert to schedules
        _migrate_schedule(conn)


def _migrate_schedule(conn):
    """Migrate old single schedule_hour/minute to new schedules array."""
    row_hour = conn.execute(
        "SELECT value FROM settings WHERE key = 'schedule_hour'"
    ).fetchone()
    row_minute = conn.execute(
        "SELECT value FROM settings WHERE key = 'schedule_minute'"
    ).fetchone()
    if row_hour and row_minute:
        row_schedules = conn.execute(
            "SELECT value FROM settings WHERE key = 'schedules'"
        ).fetchone()
        # Only migrate if schedules is still the default
        if row_schedules and row_schedules["value"] == '[{"hour": 6, "minute": 0}]':
            schedules = [{"hour": int(row_hour["value"]), "minute": int(row_minute["value"])}]
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("schedules", json.dumps(schedules)),
            )
        conn.execute("DELETE FROM settings WHERE key IN ('schedule_hour', 'schedule_minute')")


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


# --- Podcast DB ---

def add_podcast(name, artist, feed_url, artwork="", genre=""):
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO podcasts (name, artist, feed_url, artwork, genre)
               VALUES (?, ?, ?, ?, ?)""",
            (name, artist, feed_url, artwork, genre),
        )


def remove_podcast(podcast_id):
    with get_db() as conn:
        conn.execute("DELETE FROM podcasts WHERE id = ?", (podcast_id,))


def get_podcasts():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM podcasts ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]


def toggle_podcast(podcast_id, enabled):
    with get_db() as conn:
        conn.execute(
            "UPDATE podcasts SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, podcast_id),
        )
