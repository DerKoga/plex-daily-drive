import json
import logging
import os

from flask import Flask, jsonify, render_template, request

import database as db
import plex_client
import scheduler
from generator import generate_playlist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.before_request
def ensure_db():
    db.init_db()


# --- Pages ---


@app.route("/")
def index():
    return render_template("index.html")


# --- API ---


@app.route("/api/status")
def api_status():
    conn = plex_client.test_connection()
    next_run = scheduler.get_next_run()
    settings = db.get_all_settings()
    return jsonify(
        {
            "plex": conn,
            "next_run": next_run,
            "enabled": settings.get("enabled") == "true",
        }
    )


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    settings = db.get_all_settings()
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    allowed_keys = {
        "plex_url",
        "plex_token",
        "playlist_prefix",
        "music_count",
        "podcast_count",
        "music_libraries",
        "podcast_libraries",
        "schedule_hour",
        "schedule_minute",
        "enabled",
        "keep_days",
        "podcast_recent_only",
        "podcast_unplayed_only",
    }

    to_save = {}
    for key, value in data.items():
        if key in allowed_keys:
            if isinstance(value, (list, dict)):
                to_save[key] = json.dumps(value)
            else:
                to_save[key] = value

    db.save_settings(to_save)

    # Reset Plex connection if URL or token changed
    if "plex_url" in data or "plex_token" in data:
        plex_client.reset_connection()

    # Reschedule if time changed
    if "schedule_hour" in data or "schedule_minute" in data:
        scheduler.reschedule()

    return jsonify({"success": True})


@app.route("/api/libraries")
def api_libraries():
    libraries = plex_client.get_libraries()
    return jsonify(libraries)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    result = generate_playlist()
    if result:
        return jsonify({"success": True, "playlist": result})
    return jsonify({"success": False, "error": "Generation failed - check logs"}), 500


@app.route("/api/history")
def api_history():
    history = db.get_history()
    return jsonify(history)


@app.route("/api/playlists")
def api_playlists():
    prefix = db.get_setting("playlist_prefix", "Daily Drive")
    playlists = plex_client.get_playlists(prefix=prefix)
    return jsonify(playlists)


@app.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    data = request.get_json() or {}
    if "plex_url" in data:
        db.save_setting("plex_url", data["plex_url"])
    if "plex_token" in data:
        db.save_setting("plex_token", data["plex_token"])
    plex_client.reset_connection()
    result = plex_client.test_connection()
    return jsonify(result)


def create_app():
    os.makedirs(os.path.dirname(db.config.DATABASE_PATH), exist_ok=True)
    db.init_db()
    scheduler.start_scheduler()
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=True)
