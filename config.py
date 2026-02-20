import os

PLEX_URL = os.environ.get("PLEX_URL", "http://localhost:32400")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "")
SCHEDULE_HOUR = int(os.environ.get("SCHEDULE_HOUR", "6"))
SCHEDULE_MINUTE = int(os.environ.get("SCHEDULE_MINUTE", "0"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/plex_daily_drive.db")
