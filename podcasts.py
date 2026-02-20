import json
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import feedparser
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, error

import database as db

logger = logging.getLogger(__name__)


def search_itunes(query, limit=10):
    """Search for podcasts via iTunes Search API."""
    try:
        resp = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": query,
                "media": "podcast",
                "limit": limit,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", []):
            results.append({
                "id": item.get("collectionId"),
                "name": item.get("collectionName", ""),
                "artist": item.get("artistName", ""),
                "feed_url": item.get("feedUrl", ""),
                "artwork": item.get("artworkUrl100", ""),
                "genre": item.get("primaryGenreName", ""),
            })
        return results
    except Exception as e:
        logger.exception("iTunes search failed for '%s'", query)
        return []


def get_feed_episodes(feed_url, limit=5):
    """Parse RSS feed and return latest episodes."""
    try:
        feed = feedparser.parse(feed_url)
        episodes = []
        for entry in feed.entries[:limit]:
            audio_url = None
            duration = None
            for link in entry.get("links", []):
                if link.get("type", "").startswith("audio/") or link.get("href", "").endswith(".mp3"):
                    audio_url = link["href"]
                    break
            # Fallback: check enclosures
            if not audio_url:
                for enc in entry.get("enclosures", []):
                    if enc.get("type", "").startswith("audio/") or enc.get("href", "").endswith(".mp3"):
                        audio_url = enc.get("href") or enc.get("url")
                        break

            if not audio_url:
                continue

            # Parse duration
            duration_str = entry.get("itunes_duration", "")
            if duration_str:
                duration = _parse_duration(duration_str)

            pub_date = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)

            episodes.append({
                "title": entry.get("title", "Unknown"),
                "url": audio_url,
                "published": pub_date,
                "duration": duration,
                "summary": _clean_html(entry.get("summary", ""))[:200],
            })
        return episodes
    except Exception as e:
        logger.exception("Failed to parse feed: %s", feed_url)
        return []


def download_episode(podcast_name, episode, base_path):
    """Download a podcast episode to the specified path."""
    podcast_dir = os.path.join(base_path, _sanitize_filename(podcast_name))
    os.makedirs(podcast_dir, exist_ok=True)

    filename = _sanitize_filename(episode["title"]) + ".mp3"
    filepath = os.path.join(podcast_dir, filename)

    if os.path.exists(filepath):
        logger.info("Episode already exists: %s", filepath)
        return filepath

    try:
        logger.info("Downloading: %s", episode["title"])
        resp = requests.get(episode["url"], stream=True, timeout=300)
        resp.raise_for_status()

        # Write to temp file first
        temp_path = filepath + ".tmp"
        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        os.rename(temp_path, filepath)

        # Tag the MP3
        _tag_mp3(filepath, podcast_name, episode)

        logger.info("Downloaded: %s", filepath)
        return filepath
    except Exception as e:
        logger.exception("Failed to download episode: %s", episode["title"])
        # Clean up temp file
        temp_path = filepath + ".tmp"
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None


def refresh_podcasts():
    """Check all subscribed podcasts for new episodes and download them."""
    podcasts = db.get_podcasts()
    download_path = db.get_setting("podcast_download_path", "/podcasts")
    max_episodes = int(db.get_setting("podcast_max_episodes", "3"))

    total_downloaded = 0
    for podcast in podcasts:
        if not podcast["enabled"]:
            continue

        logger.info("Checking podcast: %s", podcast["name"])
        episodes = get_feed_episodes(podcast["feed_url"], limit=max_episodes)

        for episode in episodes:
            result = download_episode(podcast["name"], episode, download_path)
            if result:
                total_downloaded += 1

        # Clean up old episodes beyond max
        _cleanup_old_episodes(podcast["name"], download_path, max_episodes)

    if total_downloaded > 0:
        logger.info("Downloaded %d new episodes total", total_downloaded)

    return total_downloaded


def _cleanup_old_episodes(podcast_name, base_path, max_keep):
    """Remove oldest episodes if we have more than max_keep."""
    podcast_dir = os.path.join(base_path, _sanitize_filename(podcast_name))
    if not os.path.isdir(podcast_dir):
        return

    files = []
    for f in os.listdir(podcast_dir):
        if f.endswith(".mp3"):
            path = os.path.join(podcast_dir, f)
            files.append((path, os.path.getmtime(path)))

    # Sort by modification time, newest first
    files.sort(key=lambda x: x[1], reverse=True)

    for path, _ in files[max_keep:]:
        try:
            os.remove(path)
            logger.info("Cleaned up old episode: %s", path)
        except OSError:
            pass


def _tag_mp3(filepath, podcast_name, episode):
    """Add ID3 tags to downloaded MP3."""
    try:
        try:
            audio = MP3(filepath, ID3=ID3)
        except error:
            audio = MP3(filepath)
            audio.add_tags()

        audio.tags.add(TIT2(encoding=3, text=episode["title"]))
        audio.tags.add(TPE1(encoding=3, text=podcast_name))
        audio.tags.add(TALB(encoding=3, text=podcast_name))
        audio.tags.add(TCON(encoding=3, text="Podcast"))
        if episode.get("published"):
            audio.tags.add(TDRC(encoding=3, text=episode["published"]))
        audio.save()
    except Exception as e:
        logger.debug("Failed to tag MP3 %s: %s", filepath, e)


def _parse_duration(duration_str):
    """Parse iTunes duration string to seconds."""
    try:
        parts = str(duration_str).split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        else:
            return int(parts[0])
    except (ValueError, IndexError):
        return None


def _sanitize_filename(name):
    """Remove invalid characters from filename."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name[:200] if name else "unknown"


def _clean_html(text):
    """Strip HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text).strip()
