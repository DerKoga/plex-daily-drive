import json
import logging
import random
import time
from datetime import datetime, timedelta

import database as db
import plex_client
from podcasts import get_subscribed_podcast_names, get_todays_episodes, refresh_podcasts

logger = logging.getLogger(__name__)


def generate_playlist():
    """Generate a Daily Drive playlist mixing music and podcasts."""
    settings = db.get_all_settings()

    if settings.get("enabled") != "true":
        logger.info("Playlist generation is disabled")
        return None

    music_libraries = json.loads(settings.get("music_libraries", "[]"))
    music_count = int(settings.get("music_count", "20"))
    podcast_count = int(settings.get("podcast_count", "3"))
    prefix = settings.get("playlist_prefix", "Daily Drive")

    if not music_libraries:
        logger.warning("No music libraries configured - skipping generation")
        return None

    # Collect music tracks from Plex
    music_tracks = []
    tracks_per_lib = max(1, music_count // len(music_libraries))
    remainder = music_count % len(music_libraries)
    for i, lib_key in enumerate(music_libraries):
        count = tracks_per_lib + (1 if i < remainder else 0)
        tracks = plex_client.get_random_tracks(lib_key, count=count)
        music_tracks.extend(tracks)

    # Collect today's podcast episodes from Plex
    podcast_episodes = _get_todays_podcast_tracks(podcast_count)

    if not music_tracks and not podcast_episodes:
        logger.warning("No tracks or episodes found - skipping generation")
        return None

    # Build the Daily Drive mix: interleave podcasts between music blocks
    playlist_items = _interleave(music_tracks, podcast_episodes)

    # Create playlist name with date (DD.MM.YYYY)
    today = datetime.now().strftime("%d.%m.%Y")
    playlist_name = f"{prefix} ({today})"

    # Clean up old playlists
    _cleanup_old_playlists(prefix, int(settings.get("keep_days", "7")))

    # Delete existing playlist for today if it exists
    plex_client.delete_playlist(playlist_name)

    # Create the new playlist with optional cover
    poster_path = settings.get("playlist_poster_path", "")
    playlist = plex_client.create_playlist(
        playlist_name, playlist_items, poster_path=poster_path or None
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
            "Generated '%s': %d music + %d podcasts = %d total",
            playlist_name,
            actual_music,
            actual_podcasts,
            len(playlist_items),
        )
        return {
            "name": playlist_name,
            "total": len(playlist_items),
            "music": actual_music,
            "podcasts": actual_podcasts,
        }

    return None


def _get_todays_podcast_tracks(max_count):
    """Find today's podcast episodes in Plex.

    Strategy:
    1. Get list of subscribed podcast names from DB
    2. For each podcast, check RSS if an episode was published today
    3. If yes, search Plex for that podcast's tracks by artist name
       (we tag downloads with artist = podcast name)
    4. Take the most recently added track (= today's download)
    """
    podcast_names = get_subscribed_podcast_names()
    if not podcast_names:
        logger.info("No subscribed podcasts")
        return []

    subscribed_podcasts = db.get_podcasts()
    today_tracks = []

    for podcast in subscribed_podcasts:
        if not podcast["enabled"]:
            continue

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


def _cleanup_old_playlists(prefix, keep_days):
    """Remove playlists older than keep_days."""
    cutoff = datetime.now() - timedelta(days=keep_days)

    try:
        server = plex_client.get_server()
        for playlist in server.playlists():
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
