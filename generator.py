import json
import logging
import os
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
    music_count = int(settings.get("music_count", "20"))
    podcast_count = int(settings.get("podcast_count", "3"))
    prefix = settings.get("playlist_prefix", "Daily Drive")
    podcast_download_path = settings.get("podcast_download_path", "/podcasts")

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

    # Collect podcast episodes from Plex library
    # Find podcast files in the podcast download folder through Plex
    podcast_episodes = _get_podcast_tracks_from_plex(podcast_download_path, podcast_count)

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


def _get_podcast_tracks_from_plex(download_path, count):
    """Try to find downloaded podcast episodes in Plex libraries.

    Searches all music libraries for tracks that match podcast download paths.
    Falls back to finding the newest mp3 files in the download folder.
    """
    try:
        server = plex_client.get_server()
        # Search all libraries for recently added podcast tracks
        podcast_tracks = []
        for section in server.library.sections():
            if section.type != "artist":
                continue
            try:
                # Search for recently added tracks, sorted by date added
                tracks = section.searchTracks(
                    sort="addedAt:desc",
                    maxresults=count * 5,
                )
                for track in tracks:
                    # Check if the track's file is in the podcast download path
                    for media in track.media:
                        for part in media.parts:
                            if download_path in part.file:
                                podcast_tracks.append(track)
                                break
                    if len(podcast_tracks) >= count:
                        break
                if len(podcast_tracks) >= count:
                    break
            except Exception as e:
                logger.debug("Error searching section %s: %s", section.title, e)
                continue

        if podcast_tracks:
            logger.info("Found %d podcast tracks in Plex", len(podcast_tracks))
            return podcast_tracks[:count]

        logger.info("No podcast tracks found in Plex libraries")
        return []
    except Exception as e:
        logger.exception("Failed to get podcast tracks from Plex")
        return []


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
