"""Sourcing helpers: cookies, search queries, song bank, vet."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

CATALOG_PATH = Path("config/songs_catalog.json")

GENRE_MOOD = {
    "movies": "epic",
    "series": "emotional",
    "romance": "romance",
    "gaming": "aggressive",
    "sports": "hype",
    "racing": "aggressive",
    "anime": "epic",
    "motivation": "dark",
}


def ytdlp_cookie_args() -> list[str]:
    cookies_env = (os.environ.get("YT_COOKIES") or "").strip()
    if not cookies_env:
        return []
    try:
        if not cookies_env.startswith("#") and "\t" not in cookies_env[:120]:
            cookies_env = base64.b64decode(cookies_env).decode("utf-8", errors="ignore")
        if not cookies_env.startswith("# Netscape"):
            cookies_env = "# Netscape HTTP Cookie File\n" + cookies_env
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="ytcookies_")
        os.write(fd, cookies_env.encode())
        os.close(fd)
        return ["--cookies", path]
    except Exception:
        return []


def search_queries_for(genre: str, topic: str) -> list[str]:
    return [topic, f"{topic} scene", f"{topic} clip", f"{genre} cinematic scene"]


def vet_keyframes_with_groq(frames: list[str], title: str = "", channel: str = "") -> dict:
    return {"accept": True, "reason": "soft"}


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text()).get("songs", [])


def pick_song_from_catalog(genre: str, used: set[str] | None = None) -> dict | None:
    mood = GENRE_MOOD.get(genre, "epic")
    songs = [s for s in load_catalog() if s.get("mood") == mood]
    if not songs:
        songs = load_catalog()
    if not songs:
        return None
    used = used or set()
    fresh = [s for s in songs if s["file"] not in used]
    return (fresh or songs)[0]


def songs_bank_url(filename: str) -> str:
    return f"https://github.com/Bhupi820970/riyio-edits/releases/download/songs-bank/{filename}"


def song_credit(entry: dict | None, path: Path | None = None) -> str:
    if entry and entry.get("title"):
        return f"{entry['title']} – {entry.get('artist', '')}".strip(" –")
    return path.stem if path else "Original Mix"


def ensure_song_from_bank(genre: str, dest: Path) -> tuple[Path, dict]:
    """Download mood-matched catalog song from songs-bank release. Fail if missing."""
    entry = pick_song_from_catalog(genre)
    if not entry:
        raise RuntimeError("No song in catalog")
    url = songs_bank_url(entry["file"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-fsSL", "-o", str(dest), url], capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 50_000:
        raise RuntimeError(f"songs-bank missing {entry['file']} — run sync_songs.yml first")
    return dest, entry
