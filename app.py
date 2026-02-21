import json
import logging
import os

from flask import Flask, jsonify, render_template, request

import database as db
import plex_client
import podcasts
import scheduler
from generator import generate_playlist, generate_all_playlists

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
    next_runs = scheduler.get_next_runs()
    settings = db.get_all_settings()
    return jsonify(
        {
            "plex": conn,
            "next_run": next_run,
            "next_runs": next_runs,
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
        "schedules",
        "enabled",
        "podcast_download_path",
        "podcast_max_episodes",
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

    # Reschedule if schedules changed
    if "schedules" in data:
        scheduler.reschedule()

    return jsonify({"success": True})


@app.route("/api/libraries")
def api_libraries():
    libraries = plex_client.get_libraries()
    return jsonify(libraries)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    import time

    data = request.get_json() or {}
    user_id = data.get("user_id")

    # Refresh podcasts and scan Plex first
    try:
        downloaded = podcasts.refresh_podcasts()
        if downloaded > 0:
            plex_client.scan_all_music_libraries()
            time.sleep(30)
    except Exception as e:
        logger.exception("Pre-generation podcast refresh failed")

    if user_id:
        result = generate_playlist(user_id=int(user_id))
    else:
        result = generate_all_playlists()

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


# --- Podcast API ---


@app.route("/api/podcasts/search")
def api_podcast_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    results = podcasts.search_itunes(query)
    return jsonify(results)


@app.route("/api/podcasts", methods=["GET"])
def api_get_podcasts():
    all_podcasts = db.get_podcasts()
    return jsonify(all_podcasts)


@app.route("/api/podcasts", methods=["POST"])
def api_add_podcast():
    data = request.get_json()
    if not data or not data.get("feed_url"):
        return jsonify({"error": "feed_url required"}), 400

    db.add_podcast(
        name=data.get("name", "Unknown"),
        artist=data.get("artist", ""),
        feed_url=data["feed_url"],
        artwork=data.get("artwork", ""),
        genre=data.get("genre", ""),
    )
    return jsonify({"success": True})


@app.route("/api/podcasts/<int:podcast_id>", methods=["DELETE"])
def api_remove_podcast(podcast_id):
    db.remove_podcast(podcast_id)
    return jsonify({"success": True})


@app.route("/api/podcasts/<int:podcast_id>/toggle", methods=["POST"])
def api_toggle_podcast(podcast_id):
    data = request.get_json() or {}
    enabled = data.get("enabled", True)
    db.toggle_podcast(podcast_id, enabled)
    return jsonify({"success": True})


@app.route("/api/podcasts/<int:podcast_id>/max-episodes", methods=["POST"])
def api_set_podcast_max_episodes(podcast_id):
    data = request.get_json() or {}
    max_episodes = int(data.get("max_episodes", 3))
    db.update_podcast_max_episodes(podcast_id, max_episodes)
    return jsonify({"success": True})


@app.route("/api/podcasts/refresh", methods=["POST"])
def api_refresh_podcasts():
    count = podcasts.refresh_podcasts()
    if count > 0:
        plex_client.scan_all_music_libraries()
    return jsonify({"success": True, "downloaded": count})


@app.route("/api/podcasts/episodes")
def api_podcast_episodes():
    feed_url = request.args.get("feed_url", "")
    if not feed_url:
        return jsonify([])
    episodes = podcasts.get_feed_episodes(feed_url, limit=10)
    return jsonify(episodes)


# --- User API ---


@app.route("/api/users", methods=["GET"])
def api_get_users():
    users = db.get_users()
    # Add podcast assignments for each user
    for user in users:
        user["podcasts"] = db.get_user_podcasts(user["id"])
    return jsonify(users)


@app.route("/api/users", methods=["POST"])
def api_add_user():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400

    music_libraries = data.get("music_libraries", [])
    if isinstance(music_libraries, list):
        music_libraries = json.dumps(music_libraries)

    user_id = db.add_user(
        name=data["name"],
        plex_username=data.get("plex_username", ""),
        plex_token=data.get("plex_token", ""),
        music_count=int(data.get("music_count", 20)),
        podcast_count=int(data.get("podcast_count", 3)),
        discovery_ratio=int(data.get("discovery_ratio", 40)),
        playlist_prefix=data.get("playlist_prefix", "Daily Drive"),
        keep_days=int(data.get("keep_days", 7)),
        music_libraries=music_libraries,
    )

    # Set podcast assignments
    podcast_ids = data.get("podcast_ids", [])
    if podcast_ids:
        db.set_user_podcasts(user_id, podcast_ids)

    return jsonify({"success": True, "id": user_id})


@app.route("/api/users/<int:user_id>", methods=["PUT"])
def api_update_user(user_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    update_data = {}
    for key in ["name", "plex_username", "plex_token", "music_count",
                "podcast_count", "discovery_ratio", "playlist_prefix",
                "keep_days", "playlist_description", "enabled"]:
        if key in data:
            update_data[key] = data[key]

    if "music_libraries" in data:
        libs = data["music_libraries"]
        update_data["music_libraries"] = json.dumps(libs) if isinstance(libs, list) else libs

    if update_data:
        db.update_user(user_id, **update_data)

    # Update podcast assignments
    if "podcast_ids" in data:
        db.set_user_podcasts(user_id, data["podcast_ids"])

    # Reset user's cached server connection
    plex_client.reset_connection()

    return jsonify({"success": True})


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def api_remove_user(user_id):
    db.remove_user(user_id)
    plex_client.reset_connection()
    return jsonify({"success": True})


@app.route("/api/users/<int:user_id>/toggle", methods=["POST"])
def api_toggle_user(user_id):
    data = request.get_json() or {}
    enabled = data.get("enabled", True)
    db.toggle_user(user_id, enabled)
    return jsonify({"success": True})


@app.route("/api/users/<int:user_id>/podcasts", methods=["GET"])
def api_get_user_podcasts(user_id):
    podcast_details = db.get_user_podcast_details(user_id)
    return jsonify(podcast_details)


@app.route("/api/users/<int:user_id>/podcasts", methods=["POST"])
def api_set_user_podcasts(user_id):
    data = request.get_json()
    if not data or "podcast_ids" not in data:
        return jsonify({"error": "podcast_ids required"}), 400
    db.set_user_podcasts(user_id, data["podcast_ids"])
    return jsonify({"success": True})


@app.route("/api/plex-users")
def api_plex_users():
    """List available Plex users for selection."""
    users = plex_client.get_plex_users()
    return jsonify(users)


POSTER_DIR = "/data/covers"


def _user_poster_path(user_id):
    return os.path.join(POSTER_DIR, f"user_{user_id}.jpg")


@app.route("/api/users/<int:user_id>/poster", methods=["POST"])
def api_upload_user_poster(user_id):
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    os.makedirs(POSTER_DIR, exist_ok=True)
    poster_path = _user_poster_path(user_id)
    file.save(poster_path)
    db.update_user(user_id, poster_path=poster_path)
    return jsonify({"success": True})


@app.route("/api/users/<int:user_id>/poster", methods=["DELETE"])
def api_delete_user_poster(user_id):
    poster_path = _user_poster_path(user_id)
    if os.path.isfile(poster_path):
        os.remove(poster_path)
    db.update_user(user_id, poster_path="")
    return jsonify({"success": True})


@app.route("/api/users/<int:user_id>/poster", methods=["GET"])
def api_get_user_poster(user_id):
    from flask import send_file
    user = db.get_user(user_id)
    poster = user.get("poster_path", "") if user else ""
    if poster and os.path.isfile(poster):
        return send_file(poster, mimetype="image/jpeg")
    return jsonify({"has_poster": False}), 404


def create_app():
    os.makedirs(os.path.dirname(db.config.DATABASE_PATH), exist_ok=True)
    db.init_db()
    scheduler.start_scheduler()
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=True)
