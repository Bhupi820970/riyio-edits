"""Sourcing: YouTube download with YT_COOKIES bot-check bypass, strict 4-corner
logo rejection, 8 genres with tailored queries.

PRIMARY AI: Groq (llama-4-scout / maverick for vision vetting + scene selection).
Gemini / OpenRouter are optional fallbacks only.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import time
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

VET_PROMPT = """You are the footage checker for a fan-edit channel.
Inspect ALL FOUR CORNERS (top-left, top-right, bottom-left, bottom-right) of every frame.
REJECT any clip that has:
- Netflix, Columbia, Warner Bros, or any studio logo
- Channel bugs, editor watermarks, "CLIP KINGS", "CLIP EMPIRE"
- Burnt-in subtitles or captions
- Persistent watermarks of any kind
Accept only clean, official or full-quality scene footage suitable for re-editing.
Reply with JSON: {"accept": true/false, "reason": "short reason"}
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


def vet_keyframes_with_groq(image_urls_or_b64: list[str], title: str = "", channel: str = "") -> dict:
    """4-corner watermark vetting via Groq vision. Returns {"accept": bool, "reason": str}."""
    if not groq_available():
        return {"accept": True, "reason": "groq unavailable — soft accept"}
    content = [{"type": "text", "text": VET_PROMPT + f"\nTitle: {title}\nChannel: {channel}"}]
    for u in image_urls_or_b64[:6]:
        if u.startswith("http"):
            content.append({"type": "image_url", "image_url": {"url": u}})
        else:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{u}"}})
    messages = [{"role": "user", "content": content}]
    raw = groq_chat(messages, vision=True, max_tokens=300)
    if not raw:
        return {"accept": True, "reason": "groq call failed — soft accept"}
    try:
        # extract JSON if present
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        pass
    accept = "reject" not in raw.lower() and "false" not in raw.lower()
    return {"accept": accept, "reason": raw[:200]}


def select_scene_with_groq(descriptions: list[str]) -> int:
    """Pick best scene index for the edit using Groq text model. Returns 0-based index."""
    if not groq_available() or not descriptions:
        return 0
    prompt = ("Pick the single best scene index (0-based) for a cinematic fan-edit. "
              "Reply with only the integer.\n\n" +
              "\n".join(f"{i}: {d}" for i, d in enumerate(descriptions)))
    raw = groq_chat([{"role": "user", "content": prompt}], vision=False, max_tokens=16)
    if not raw:
        return 0
    try:
        return max(0, min(int("".join(c for c in raw if c.isdigit()) or "0"), len(descriptions) - 1))
    except Exception:
        return 0
