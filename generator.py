import json
import logging
import random
from datetime import datetime, timedelta

import database as db
import plex_client

logger = logging.getLogger(__name__)


def generate_playlist():
    """Generate a Daily Drive playlist mixing music and podcasts."""
    settings = db.get_all_settings()

    if settings.get("enabled") != "true":
        logger.info("Playlist generation is disabled")
        return None

    music_libraries = json.loads(settings.get("music_libraries", "[]"))
    podcast_libraries = json.loads(settings.get("podcast_libraries", "[]"))
    music_count = int(settings.get("music_count", "20"))
    podcast_count = int(settings.get("podcast_count", "3"))
    prefix = settings.get("playlist_prefix", "Daily Drive")
    recent_only = settings.get("podcast_recent_only", "true") == "true"
    unplayed_only = settings.get("podcast_unplayed_only", "true") == "true"

    if not music_libraries and not podcast_libraries:
        logger.warning("No libraries configured - skipping generation")
        return None

    # Collect music tracks
    music_tracks = []
    if music_libraries:
        tracks_per_lib = max(1, music_count // len(music_libraries))
        remainder = music_count % len(music_libraries)
        for i, lib_key in enumerate(music_libraries):
            count = tracks_per_lib + (1 if i < remainder else 0)
            tracks = plex_client.get_random_tracks(lib_key, count=count)
            music_tracks.extend(tracks)

    # Collect podcast episodes
    podcast_episodes = []
    if podcast_libraries:
        eps_per_lib = max(1, podcast_count // len(podcast_libraries))
        remainder = podcast_count % len(podcast_libraries)
        for i, lib_key in enumerate(podcast_libraries):
            count = eps_per_lib + (1 if i < remainder else 0)
            episodes = plex_client.get_podcast_episodes(
                lib_key,
                recent_only=recent_only,
                unplayed_only=unplayed_only,
                count=count,
            )
            podcast_episodes.extend(episodes)

    if not music_tracks and not podcast_episodes:
        logger.warning("No tracks or episodes found - skipping generation")
        return None

    # Build the Daily Drive mix: interleave podcasts between music blocks
    playlist_items = _interleave(music_tracks, podcast_episodes)

    # Create playlist name with date
    today = datetime.now().strftime("%Y-%m-%d")
    playlist_name = f"{prefix} - {today}"

    # Clean up old playlists
    _cleanup_old_playlists(prefix, int(settings.get("keep_days", "7")))

    # Delete existing playlist for today if it exists
    plex_client.delete_playlist(playlist_name)

    # Create the new playlist
    playlist = plex_client.create_playlist(playlist_name, playlist_items)

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
    random.shuffle(podcast_episodes)

    result = []
    num_podcasts = len(podcast_episodes)
    # Split music into (num_podcasts + 1) roughly equal blocks
    block_size = max(1, len(music_tracks) // (num_podcasts + 1))

    music_idx = 0
    for i, episode in enumerate(podcast_episodes):
        # Add a block of music
        end = min(music_idx + block_size, len(music_tracks))
        result.extend(music_tracks[music_idx:end])
        music_idx = end
        # Add the podcast episode
        result.append(episode)

    # Add remaining music tracks
    result.extend(music_tracks[music_idx:])

    return result


def _cleanup_old_playlists(prefix, keep_days):
    """Remove playlists older than keep_days."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    try:
        server = plex_client.get_server()
        for playlist in server.playlists():
            if not playlist.title.startswith(prefix + " - "):
                continue
            # Extract date from playlist name
            date_part = playlist.title.replace(prefix + " - ", "")
            try:
                if date_part < cutoff_str:
                    playlist.delete()
                    logger.info("Cleaned up old playlist: %s", playlist.title)
            except ValueError:
                continue
    except Exception as e:
        logger.exception("Failed to cleanup old playlists")
