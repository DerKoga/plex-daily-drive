import json
import logging
import random
import time
from datetime import datetime, timedelta

import database as db
import plex_client
from podcasts import get_subscribed_podcast_names, get_todays_episodes, refresh_podcasts

logger = logging.getLogger(__name__)


def generate_playlist(user_id=None):
    """Generate a Daily Drive playlist.

    If user_id is given, generate for that specific user using their settings,
    podcast selections, and Plex play history.
    If user_id is None, generate using global settings (legacy/default behavior).
    """
    if user_id:
        return _generate_for_user(user_id)
    return _generate_global()


def generate_all_playlists():
    """Generate playlists for all enabled users. Falls back to global if no users exist."""
    users = db.get_users()
    enabled_users = [u for u in users if u["enabled"]]

    if not enabled_users:
        # No users configured - use global/legacy mode
        return generate_playlist()

    results = []
    for user in enabled_users:
        try:
            result = _generate_for_user(user["id"])
            if result:
                results.append(result)
        except Exception as e:
            logger.exception("Failed to generate playlist for user '%s'", user["name"])

    return results if results else None


def _generate_global():
    """Generate playlist using global settings (original behavior)."""
    settings = db.get_all_settings()

    if settings.get("enabled") != "true":
        logger.info("Playlist generation is disabled")
        return None

    music_libraries = json.loads(settings.get("music_libraries", "[]"))
    music_count = int(settings.get("music_count", "20"))
    podcast_count = int(settings.get("podcast_count", "3"))
    prefix = settings.get("playlist_prefix", "Daily Drive")
    discovery_ratio = int(settings.get("discovery_ratio", "40"))
    keep_days = int(settings.get("keep_days", "7"))
    poster_path = settings.get("playlist_poster_path", "")
    description = settings.get("playlist_description", "")

    return _do_generate(
        music_libraries=music_libraries,
        music_count=music_count,
        podcast_count=podcast_count,
        prefix=prefix,
        discovery_ratio=discovery_ratio,
        keep_days=keep_days,
        poster_path=poster_path,
        description=description,
        server=None,
        user_podcasts=None,
    )


def _generate_for_user(user_id):
    """Generate playlist for a specific user."""
    user = db.get_user(user_id)
    if not user:
        logger.warning("User %d not found", user_id)
        return None

    if not user["enabled"]:
        logger.info("User '%s' is disabled, skipping", user["name"])
        return None

    music_libraries = json.loads(user.get("music_libraries", "[]"))
    music_count = int(user.get("music_count", 20))
    podcast_count = int(user.get("podcast_count", 3))
    prefix = user.get("playlist_prefix", "Daily Drive")
    discovery_ratio = int(user.get("discovery_ratio", 40))
    keep_days = int(user.get("keep_days", 7))

    # Get user-specific server connection
    server = plex_client.get_server_for_user(user)

    # Get user's podcast subscriptions
    user_podcast_list = db.get_user_podcast_details(user_id)

    # Use user-specific poster and description
    poster_path = user.get("poster_path", "")
    description = user.get("playlist_description", "")

    logger.info("Generating playlist for user '%s'", user["name"])

    return _do_generate(
        music_libraries=music_libraries,
        music_count=music_count,
        podcast_count=podcast_count,
        prefix=prefix,
        discovery_ratio=discovery_ratio,
        keep_days=keep_days,
        poster_path=poster_path,
        description=description,
        server=server,
        user_podcasts=user_podcast_list,
        user_name=user["name"],
    )


def _do_generate(music_libraries, music_count, podcast_count, prefix,
                 discovery_ratio, keep_days, poster_path, description,
                 server=None, user_podcasts=None, user_name=None):
    """Core playlist generation logic, shared between global and per-user modes."""

    if not music_libraries:
        logger.warning("No music libraries configured - skipping generation%s",
                       f" for user '{user_name}'" if user_name else "")
        return None

    # Smart music selection: split between favorites and discoveries
    discovery_ratio = max(0, min(100, discovery_ratio))  # clamp 0-100
    discovery_count = round(music_count * discovery_ratio / 100)
    favorites_count = music_count - discovery_count

    music_tracks = []
    num_libs = len(music_libraries)

    # Collect favorites (frequently played tracks)
    if favorites_count > 0:
        fav_per_lib = max(1, favorites_count // num_libs)
        fav_remainder = favorites_count % num_libs
        for i, lib_key in enumerate(music_libraries):
            count = fav_per_lib + (1 if i < fav_remainder else 0)
            tracks = plex_client.get_favorite_tracks(lib_key, count=count, server=server)
            music_tracks.extend(tracks)

    # Collect discoveries (unplayed / new tracks)
    if discovery_count > 0:
        disc_per_lib = max(1, discovery_count // num_libs)
        disc_remainder = discovery_count % num_libs
        for i, lib_key in enumerate(music_libraries):
            count = disc_per_lib + (1 if i < disc_remainder else 0)
            tracks = plex_client.get_discovery_tracks(lib_key, count=count, server=server)
            music_tracks.extend(tracks)

    logger.info("Music selection: %d favorites + %d discoveries (ratio %d%%)%s",
                favorites_count, discovery_count, discovery_ratio,
                f" for user '{user_name}'" if user_name else "")

    # Collect today's podcast episodes from Plex
    podcast_episodes = _get_todays_podcast_tracks(podcast_count, user_podcasts=user_podcasts)

    if not music_tracks and not podcast_episodes:
        logger.warning("No tracks or episodes found - skipping generation")
        return None

    # Build the Daily Drive mix: interleave podcasts between music blocks
    playlist_items = _interleave(music_tracks, podcast_episodes)

    # Create playlist name with date (DD.MM.YYYY)
    today = datetime.now().strftime("%d.%m.%Y")
    playlist_name = f"{prefix} ({today})"

    # Clean up old playlists
    _cleanup_old_playlists(prefix, keep_days, server=server)

    # Update existing playlist or create a new one
    playlist = plex_client.update_or_create_playlist(
        playlist_name,
        playlist_items,
        poster_path=poster_path or None,
        description=description or None,
        server=server,
    )

    if playlist:
        actual_music = len(music_tracks)
        actual_podcasts = len(podcast_episodes)
        db.add_history(
            playlist_name,
            len(playlist_items),
            actual_podcasts,
            actual_music,
        )
        logger.info(
            "Generated '%s': %d music + %d podcasts = %d total%s",
            playlist_name,
            actual_music,
            actual_podcasts,
            len(playlist_items),
            f" (user: {user_name})" if user_name else "",
        )
        return {
            "name": playlist_name,
            "total": len(playlist_items),
            "music": actual_music,
            "podcasts": actual_podcasts,
            "user": user_name,
        }

    return None


def _get_todays_podcast_tracks(max_count, user_podcasts=None):
    """Find today's podcast episodes in Plex.

    If user_podcasts is provided, only check those podcasts.
    Otherwise, check all enabled subscribed podcasts (global mode).
    """
    if user_podcasts is not None:
        # User-specific mode: use the user's podcast list
        podcasts_to_check = [p for p in user_podcasts if p.get("enabled", 1)]
    else:
        # Global mode: all enabled podcasts
        podcast_names = get_subscribed_podcast_names()
        if not podcast_names:
            logger.info("No subscribed podcasts")
            return []
        podcasts_to_check = [p for p in db.get_podcasts() if p["enabled"]]

    if not podcasts_to_check:
        logger.info("No podcasts to check")
        return []

    today_tracks = []

    for podcast in podcasts_to_check:
        # Check RSS: did this podcast publish today?
        todays_episodes = get_todays_episodes(podcast["feed_url"])
        if not todays_episodes:
            logger.info("No episode today for: %s", podcast["name"])
            continue

        logger.info(
            "Podcast '%s' has %d episode(s) today, searching Plex...",
            podcast["name"],
            len(todays_episodes),
        )

        # Find this podcast's tracks in Plex by artist name
        tracks = plex_client.find_tracks_by_artist(podcast["name"], max_results=3)
        if tracks:
            # Take the most recently added one (should be today's episode)
            today_tracks.append(tracks[0])
            logger.info(
                "Found Plex track for '%s': %s",
                podcast["name"],
                tracks[0].title,
            )
        else:
            logger.warning(
                "Podcast '%s' has today's episode but not found in Plex. "
                "Make sure the podcast download folder is in a Plex music library "
                "and Plex has scanned it.",
                podcast["name"],
            )

        if len(today_tracks) >= max_count:
            break

    logger.info("Found %d podcast tracks for today", len(today_tracks))
    return today_tracks


def _interleave(music_tracks, podcast_episodes):
    """Interleave podcast episodes between blocks of music tracks.

    Creates a pattern like: [music block] [podcast] [music block] [podcast] ...
    Similar to Spotify's Daily Drive format.
    """
    if not podcast_episodes:
        return list(music_tracks)
    if not music_tracks:
        return list(podcast_episodes)

    random.shuffle(music_tracks)
    # Don't shuffle podcasts - keep them in order

    result = []
    num_podcasts = len(podcast_episodes)
    block_size = max(1, len(music_tracks) // (num_podcasts + 1))

    music_idx = 0
    for i, episode in enumerate(podcast_episodes):
        end = min(music_idx + block_size, len(music_tracks))
        result.extend(music_tracks[music_idx:end])
        music_idx = end
        result.append(episode)

    # Add remaining music tracks
    result.extend(music_tracks[music_idx:])

    return result


def _cleanup_old_playlists(prefix, keep_days, server=None):
    """Remove playlists older than keep_days."""
    cutoff = datetime.now() - timedelta(days=keep_days)

    try:
        srv = server or plex_client.get_server()
        for playlist in srv.playlists():
            if not playlist.title.startswith(prefix):
                continue
            # Parse date from both formats:
            # New: "Daily Drive (21.02.2025)"
            # Old: "Daily Drive - 2025-02-21"
            title = playlist.title
            try:
                if "(" in title and title.endswith(")"):
                    date_str = title.split("(")[-1].rstrip(")")
                    playlist_date = datetime.strptime(date_str, "%d.%m.%Y")
                elif " - " in title:
                    date_str = title.split(" - ")[-1]
                    playlist_date = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    continue
                if playlist_date < cutoff:
                    playlist.delete()
                    logger.info("Cleaned up old playlist: %s", playlist.title)
            except ValueError:
                continue
    except Exception as e:
        logger.exception("Failed to cleanup old playlists")
