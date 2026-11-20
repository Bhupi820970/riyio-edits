"""Sourcing: YouTube download with YT_COOKIES bot-check bypass, strict 4-corner
logo rejection, 8 genres with tailored queries.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from pathlib import Path

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

VET_PROMPT = """You are the footage checker for a fan-edit channel.
Inspect ALL FOUR CORNERS (top-left, top-right, bottom-left, bottom-right) of every frame.
REJECT any clip that has:
- Netflix, Columbia, Warner Bros, or any studio logo
- Channel bugs, editor watermarks, "CLIP KINGS", "CLIP EMPIRE"
- Burnt-in subtitles or captions
- Persistent watermarks of any kind
Accept only clean, official or full-quality scene footage suitable for re-editing.
"""


def ytdlp_cookie_args() -> list[str]:
    """If YT_COOKIES (raw Netscape or base64) is set, write to temp and return --cookies path."""
    cookies_env = (os.environ.get("YT_COOKIES") or "").strip()
    if not cookies_env:
        return []
    try:
        if not cookies_env.startswith("#") and "\t" not in cookies_env[:80]:
            cookies_env = base64.b64decode(cookies_env).decode("utf-8", errors="ignore")
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="ytcookies_")
        os.write(fd, cookies_env.encode())
        os.close(fd)
        return ["--cookies", path]
    except Exception:
        return []


def is_blocked_channel(channel: str) -> bool:
    c = (channel or "").lower()
    return any(b in c for b in BLOCKED_CHANNELS)


def search_queries_for(genre: str, topic: str) -> list[str]:
    base = GENRE_QUERIES.get(genre, ["cinematic scene"])
    return [topic, f"{topic} official", f"{topic} full scene"] + base[:2]


def keyframes_cmd(path: str, out: str, width: int = 960) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error", "-i", path, "-vf", f"scale={width}:-2",
            "-q:v", "3", "-frames:v", "1", out]
