import logging

from plexapi.server import PlexServer

import config

logger = logging.getLogger(__name__)

_server = None


def get_server():
    global _server
    if _server is None:
        _server = PlexServer(config.PLEX_URL, config.PLEX_TOKEN)
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


def get_music_libraries():
    return [lib for lib in get_libraries() if lib["type"] == "artist"]


def get_podcast_libraries():
    return [lib for lib in get_libraries() if lib["type"] == "artist"]


def get_random_tracks(library_key, count=20):
    try:
        server = get_server()
        section = server.library.sectionByID(int(library_key))
        # Search for all tracks and pick random ones
        all_tracks = section.searchTracks(sort="random", maxresults=count)
        return all_tracks
    except Exception as e:
        logger.exception("Failed to get random tracks from library %s", library_key)
        return []


def get_podcast_episodes(library_key, recent_only=True, unplayed_only=True, count=3):
    try:
        server = get_server()
        section = server.library.sectionByID(int(library_key))

        filters = {}
        sort = "addedAt:desc" if recent_only else "random"

        if unplayed_only:
            # Get tracks that haven't been fully played
            episodes = section.searchTracks(
                sort=sort,
                maxresults=count * 3,
                **filters,
            )
            # Filter to unplayed episodes
            unplayed = [ep for ep in episodes if not getattr(ep, "viewCount", 0)]
            return unplayed[:count]
        else:
            episodes = section.searchTracks(
                sort=sort,
                maxresults=count,
                **filters,
            )
            return list(episodes)
    except Exception as e:
        logger.exception(
            "Failed to get podcast episodes from library %s", library_key
        )
        return []


def create_playlist(name, items):
    try:
        server = get_server()
        playlist = server.createPlaylist(name, items=items)
        logger.info("Created playlist '%s' with %d items", name, len(items))
        return playlist
    except Exception as e:
        logger.exception("Failed to create playlist '%s'", name)
        return None


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
