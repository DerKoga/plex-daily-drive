import logging
import os
import random
from urllib.parse import urlparse

import requests
from plexapi.server import PlexServer

import config
import database as db

logger = logging.getLogger(__name__)

_server = None
_user_servers = {}


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


def get_server_for_user(user):
    """Get a PlexServer connection for a specific user.

    If the user has a plex_token, use it directly.
    If the user has a plex_username, use switchUser.
    Falls back to the admin server.
    """
    global _user_servers

    user_id = user["id"]
    if user_id in _user_servers:
        return _user_servers[user_id]

    try:
        if user.get("plex_token"):
            url = _get_plex_url()
            session = _make_session(url)
            server = PlexServer(url, user["plex_token"], session=session)
            _user_servers[user_id] = server
            return server

        if user.get("plex_username"):
            admin_server = get_server()
            server = admin_server.switchUser(user["plex_username"])
            _user_servers[user_id] = server
            return server
    except Exception as e:
        logger.exception(
            "Failed to get server for user '%s', falling back to admin",
            user.get("name", "?"),
        )

    return get_server()


def get_plex_users():
    """List all users available on the Plex server (for user selection)."""
    try:
        server = get_server()
        account = server.myPlexAccount()
        users = [{"username": account.username, "title": account.title, "is_admin": True}]
        for user in account.users():
            users.append({
                "username": user.username or user.title,
                "title": user.title,
                "is_admin": False,
            })
        return users
    except Exception as e:
        logger.exception("Failed to list Plex users")
        return []


def reset_connection():
    global _server, _user_servers
    _server = None
    _user_servers = {}


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


def get_random_tracks(library_key, count=20, server=None):
    try:
        srv = server or get_server()
        section = srv.library.sectionByID(int(library_key))
        all_tracks = section.searchTracks(sort="random", maxresults=count)
        return all_tracks
    except Exception as e:
        logger.exception("Failed to get random tracks from library %s", library_key)
        return []


def get_favorite_tracks(library_key, count=10, server=None):
    """Get frequently played / highly rated tracks from a library.

    Fetches the most-played tracks and randomly samples from them
    to add variety while staying within the user's favorites.
    Falls back to random tracks if no play history exists.
    """
    try:
        srv = server or get_server()
        section = srv.library.sectionByID(int(library_key))
        pool_size = count * 5

        # Get most-played tracks
        played = section.searchTracks(sort="viewCount:desc", maxresults=pool_size)

        # Filter to tracks actually played at least once
        played = [t for t in played if getattr(t, "viewCount", 0) and t.viewCount > 0]

        if not played:
            logger.info("No play history in library %s, falling back to random", library_key)
            return get_random_tracks(library_key, count, server=srv)

        # Randomly sample from the favorites pool
        sample_size = min(count, len(played))
        selected = random.sample(played, sample_size)
        logger.debug("Selected %d favorites from %d played tracks (library %s)",
                      len(selected), len(played), library_key)
        return selected
    except Exception as e:
        logger.exception("Failed to get favorite tracks from library %s", library_key)
        return get_random_tracks(library_key, count, server=server)


def get_discovery_tracks(library_key, count=10, server=None):
    """Get tracks the user hasn't listened to yet.

    Fetches recently added tracks that have never been played.
    Falls back to random tracks if not enough unplayed tracks exist.
    """
    try:
        srv = server or get_server()
        section = srv.library.sectionByID(int(library_key))
        pool_size = count * 10

        # Get recently added tracks
        recent = section.searchTracks(sort="addedAt:desc", maxresults=pool_size)

        # Filter to unplayed tracks (viewCount == 0 or None)
        unplayed = [t for t in recent if not getattr(t, "viewCount", 0)]

        if len(unplayed) < count:
            # Try a larger random pool to find more unplayed tracks
            random_pool = section.searchTracks(sort="random", maxresults=pool_size)
            for t in random_pool:
                if not getattr(t, "viewCount", 0) and t not in unplayed:
                    unplayed.append(t)
                    if len(unplayed) >= count * 3:
                        break

        if not unplayed:
            logger.info("No unplayed tracks in library %s, falling back to random", library_key)
            return get_random_tracks(library_key, count, server=srv)

        sample_size = min(count, len(unplayed))
        selected = random.sample(unplayed, sample_size)
        logger.debug("Selected %d discoveries from %d unplayed tracks (library %s)",
                      len(selected), len(unplayed), library_key)
        return selected
    except Exception as e:
        logger.exception("Failed to get discovery tracks from library %s", library_key)
        return get_random_tracks(library_key, count, server=server)


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


def create_playlist(name, items, poster_path=None, description=None, server=None):
    try:
        srv = server or get_server()
        playlist = srv.createPlaylist(name, items=items)
        logger.info("Created playlist '%s' with %d items", name, len(items))
        _apply_playlist_metadata(playlist, poster_path, description)
        return playlist
    except Exception as e:
        logger.exception("Failed to create playlist '%s'", name)
        return None


def update_or_create_playlist(name, items, poster_path=None, description=None, server=None):
    """Update an existing playlist's items or create a new one if it doesn't exist."""
    try:
        srv = server or get_server()
        existing = None
        for playlist in srv.playlists():
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
            return create_playlist(name, items, poster_path, description, server=srv)
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


def delete_playlist(name, server=None):
    try:
        srv = server or get_server()
        for playlist in srv.playlists():
            if playlist.title == name:
                playlist.delete()
                logger.info("Deleted playlist '%s'", name)
                return True
        return False
    except Exception as e:
        logger.exception("Failed to delete playlist '%s'", name)
        return False


def get_playlists(prefix=None, server=None):
    try:
        srv = server or get_server()
        playlists = srv.playlists()
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
