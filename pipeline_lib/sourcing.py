"""Sourcing helpers: cookies, genres, song bank pick from catalog."""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path

from .groq_client import chat as groq_chat, available as groq_available

BLOCKED_CHANNELS = {"clip kings", "clip empire"}

GENRES = ["movies", "series", "romance", "gaming", "sports", "racing", "anime", "motivation"]

GENRE_QUERIES = {
    "movies": ["epic movie scene full", "cinematic dialogue scene", "blockbuster movie moment"],
    "series": ["tv series emotional scene", "series best dialogue", "tv show full scene"],
    "romance": ["romantic movie scene", "love confession scene", "heartfelt couple moment"],
    "gaming": ["gta cinematic", "open world game trailer scene", "epic gaming moment"],
    "sports": ["athlete interview full", "sports press conference", "championship moment"],
    "racing": ["f1 race highlight", "car chase cinematic", "racing movie scene"],
    "anime": ["anime emotional scene full", "anime fight scene no sub", "anime best moment"],
    "motivation": ["motivational speech scene", "inspirational movie quote", "underdog story scene"],
}

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

VET_PROMPT = """You are the footage checker for a fan-edit channel.
Inspect ALL FOUR CORNERS of every frame.
REJECT any clip with Netflix/Columbia/Warner logos, channel bugs, editor watermarks, or burnt-in subtitles.
Accept only clean scene footage.
Reply with JSON: {"accept": true/false, "reason": "short reason"}
"""

REPO = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO / "config" / "songs_catalog.json"


def ytdlp_cookie_args() -> list[str]:
    cookies_env = (os.environ.get("YT_COOKIES") or "").strip()
    if not cookies_env:
        return []
    try:
        if not cookies_env.startswith("#") and "\t" not in cookies_env[:120]:
            cookies_env = base64.b64decode(cookies_env).decode("utf-8", errors="ignore")
        if not cookies_env.startswith("# Netscape") and not cookies_env.startswith("# HTTP Cookie File"):
            cookies_env = "# Netscape HTTP Cookie File\n" + cookies_env
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="ytcookies_")
        os.write(fd, cookies_env.encode())
        os.close(fd)
        os.chmod(path, 0o600)
        return ["--cookies", path]
    except Exception as e:
        print("cookie write failed:", e)
        return []


def is_blocked_channel(channel: str) -> bool:
    c = (channel or "").lower()
    return any(b in c for b in BLOCKED_CHANNELS)


def search_queries_for(genre: str, topic: str) -> list[str]:
    base = GENRE_QUERIES.get(genre, ["cinematic scene"])
    return [topic, f"{topic} official", f"{topic} full scene"] + base[:2]


def load_catalog() -> list[dict]:
    if CATALOG_PATH.exists():
        try:
            return json.loads(CATALOG_PATH.read_text())["songs"]
        except Exception:
            pass
    return []


def pick_song_from_bank(genre: str, songs_dir: Path, history: dict | None = None) -> tuple[Path | None, dict | None]:
    """Pick a non-repeating mood-matched mp3 from local songs/ (synced from songs-bank)."""
    mood = GENRE_MOOD.get(genre, "epic")
    catalog = load_catalog()
    used = set((history or {}).get("songs", []))
    # Prefer catalog entries of matching mood that exist on disk and aren't recently used
    for entry in catalog:
        if entry.get("mood") != mood:
            continue
        p = songs_dir / entry["file"]
        if p.exists() and entry["file"] not in used:
            return p, entry
    # Fallback: any matching mood file on disk
    for p in songs_dir.glob(f"{mood}_*.mp3"):
        if p.name not in used:
            return p, None
    # Last resort: any mp3
    for p in songs_dir.glob("*.mp3"):
        return p, None
    return None, None


def song_credit(entry: dict | None, path: Path | None) -> str:
    if entry:
        return f"{entry.get('title', '')} – {entry.get('artist', '')}".strip(" –")
    if path:
        return path.stem
    return "Original Mix"


def vet_keyframes_with_groq(image_urls_or_b64: list[str], title: str = "", channel: str = "") -> dict:
    if not groq_available():
        return {"accept": True, "reason": "groq unavailable — soft accept"}
    content = [{"type": "text", "text": VET_PROMPT + f"\nTitle: {title}\nChannel: {channel}"}]
    for u in image_urls_or_b64[:6]:
        if u.startswith("http"):
            content.append({"type": "image_url", "image_url": {"url": u}})
        else:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{u}"}})
    raw = groq_chat([{"role": "user", "content": content}], vision=True, max_tokens=300)
    if not raw:
        return {"accept": True, "reason": "groq call failed — soft accept"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        pass
    accept = "reject" not in raw.lower() and "false" not in raw.lower()
    return {"accept": accept, "reason": raw[:200]}
