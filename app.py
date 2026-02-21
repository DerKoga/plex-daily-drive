import json
import logging
import os

from flask import Flask, jsonify, render_template, request

import database as db
import plex_client
import podcasts
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
        "playlist_prefix",
        "music_count",
        "podcast_count",
        "music_libraries",
        "podcast_libraries",
        "schedules",
        "enabled",
        "keep_days",
        "podcast_recent_only",
        "podcast_unplayed_only",
        "podcast_download_path",
        "podcast_max_episodes",
        "playlist_description",
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

    # Refresh podcasts and scan Plex first
    try:
        downloaded = podcasts.refresh_podcasts()
        if downloaded > 0:
            plex_client.scan_all_music_libraries()
            time.sleep(30)
    except Exception as e:
        logger.exception("Pre-generation podcast refresh failed")

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


POSTER_PATH = "/data/playlist_cover.jpg"


@app.route("/api/poster", methods=["POST"])
def api_upload_poster():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    file.save(POSTER_PATH)
    db.save_setting("playlist_poster_path", POSTER_PATH)
    return jsonify({"success": True})


@app.route("/api/poster", methods=["DELETE"])
def api_delete_poster():
    if os.path.isfile(POSTER_PATH):
        os.remove(POSTER_PATH)
    db.save_setting("playlist_poster_path", "")
    return jsonify({"success": True})


@app.route("/api/poster", methods=["GET"])
def api_get_poster():
    poster = db.get_setting("playlist_poster_path", "")
    if poster and os.path.isfile(poster):
        from flask import send_file
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
