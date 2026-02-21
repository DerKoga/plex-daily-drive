import logging
import os
from urllib.parse import urlparse

import requests
from plexapi.server import PlexServer

import config
import database as db

logger = logging.getLogger(__name__)

_server = None


def _get_plex_url():
    """Get Plex URL from DB settings, falling back to env var."""
    url = db.get_setting("plex_url")
    return url if url else config.PLEX_URL


def _get_plex_token():
    """Get Plex token from DB settings, falling back to env var."""
    token = db.get_setting("plex_token")
    return token if token else config.PLEX_TOKEN


def _make_session(url):
    """Create a requests session, disabling SSL verification for local/HTTPS connections."""
    session = requests.Session()
    parsed = urlparse(url)
    if parsed.scheme == "https":
        session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return session


def get_server():
    global _server
    if _server is None:
        url = _get_plex_url()
        session = _make_session(url)
        _server = PlexServer(url, _get_plex_token(), session=session)
    return _server


def reset_connection():
    global _server
    _server = None


def test_connection():
    try:
        reset_connection()
        server = get_server()
        return {
            "success": True,
            "server_name": server.friendlyName,
            "version": server.version,
        }
    except Exception as e:
        logger.exception("Failed to connect to Plex")
        return {"success": False, "error": str(e)}


def get_libraries():
    try:
        server = get_server()
        libraries = []
        for section in server.library.sections():
            libraries.append(
                {
                    "key": section.key,
                    "title": section.title,
                    "type": section.type,
                }
            )
        return libraries
    except Exception as e:
        logger.exception("Failed to get libraries")
        return []


def get_random_tracks(library_key, count=20):
    try:
        server = get_server()
        section = server.library.sectionByID(int(library_key))
        all_tracks = section.searchTracks(sort="random", maxresults=count)
        return all_tracks
    except Exception as e:
        logger.exception("Failed to get random tracks from library %s", library_key)
        return []


def find_tracks_by_artist(artist_name, max_results=5):
    """Search ALL music libraries for tracks by a specific artist name.

    This is used to find downloaded podcast episodes in Plex by their
    tagged artist name (= podcast name).
    """
    try:
        server = get_server()
        found = []
        for section in server.library.sections():
            if section.type != "artist":
                continue
            try:
                tracks = section.searchTracks(
                    **{"artist.title": artist_name},
                    sort="addedAt:desc",
                    maxresults=max_results,
                )
                found.extend(tracks)
            except Exception:
                # Fallback: broader search
                try:
                    tracks = section.searchTracks(
                        title="",
                        sort="addedAt:desc",
                        maxresults=max_results * 10,
                    )
                    for t in tracks:
                        if t.grandparentTitle == artist_name or (
                            hasattr(t, "originalTitle")
                            and t.originalTitle == artist_name
                        ):
                            found.append(t)
                            if len(found) >= max_results:
                                break
                except Exception as inner_e:
                    logger.debug(
                        "Fallback search failed for '%s' in %s: %s",
                        artist_name,
                        section.title,
                        inner_e,
                    )
        return found
    except Exception as e:
        logger.exception("Failed to find tracks by artist '%s'", artist_name)
        return []


def scan_library(library_key):
    """Trigger a Plex library scan."""
    try:
        server = get_server()
        section = server.library.sectionByID(int(library_key))
        section.update()
        logger.info("Triggered scan for library: %s", section.title)
    except Exception as e:
        logger.exception("Failed to scan library %s", library_key)


def scan_all_music_libraries():
    """Trigger a scan on all music libraries."""
    try:
        server = get_server()
        for section in server.library.sections():
            if section.type == "artist":
                section.update()
                logger.info("Triggered scan for library: %s", section.title)
    except Exception as e:
        logger.exception("Failed to scan music libraries")


def create_playlist(name, items, poster_path=None, description=None):
    try:
        server = get_server()
        playlist = server.createPlaylist(name, items=items)
        logger.info("Created playlist '%s' with %d items", name, len(items))
        _apply_playlist_metadata(playlist, poster_path, description)
        return playlist
    except Exception as e:
        logger.exception("Failed to create playlist '%s'", name)
        return None


def update_or_create_playlist(name, items, poster_path=None, description=None):
    """Update an existing playlist's items or create a new one if it doesn't exist."""
    try:
        server = get_server()
        existing = None
        for playlist in server.playlists():
            if playlist.title == name:
                existing = playlist
                break

        if existing:
            # Remove all current items
            current_items = existing.items()
            if current_items:
                existing.removeItems(current_items)
            # Add new items
            if items:
                existing.addItems(items)
            logger.info("Updated playlist '%s' with %d items", name, len(items))
            _apply_playlist_metadata(existing, poster_path, description)
            return existing
        else:
            # No existing playlist, create a new one
            return create_playlist(name, items, poster_path, description)
    except Exception as e:
        logger.exception("Failed to update/create playlist '%s'", name)
        return None


def _apply_playlist_metadata(playlist, poster_path=None, description=None):
    """Apply poster and description to a playlist."""
    if poster_path and os.path.isfile(poster_path):
        try:
            playlist.uploadPoster(filepath=poster_path)
            logger.info("Set poster for playlist '%s'", playlist.title)
        except Exception as e:
            logger.warning("Failed to set poster for '%s': %s", playlist.title, e)
    if description is not None:
        try:
            playlist.editSummary(description)
            logger.info("Set description for playlist '%s'", playlist.title)
        except Exception as e:
            logger.warning("Failed to set description for '%s': %s", playlist.title, e)


def delete_playlist(name):
    try:
        server = get_server()
        for playlist in server.playlists():
            if playlist.title == name:
                playlist.delete()
                logger.info("Deleted playlist '%s'", name)
                return True
        return False
    except Exception as e:
        logger.exception("Failed to delete playlist '%s'", name)
        return False


def get_playlists(prefix=None):
    try:
        server = get_server()
        playlists = server.playlists()
        if prefix:
            playlists = [p for p in playlists if p.title.startswith(prefix)]
        return [
            {
                "title": p.title,
                "duration": p.duration,
                "item_count": len(p.items()),
                "added_at": str(p.addedAt) if p.addedAt else None,
            }
            for p in playlists
        ]
    except Exception as e:
        logger.exception("Failed to get playlists")
        return []
