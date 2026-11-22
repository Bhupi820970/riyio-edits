"""Clean sourcing via RapidAPI + songs-bank with mood fallback."""
from __future__ import annotations
import json, os, subprocess
from pathlib import Path

BLACKLIST = {
    "netflix", "crunchyroll", "prime video", "amazon prime", "hbo", "disney",
    "marvel entertainment", "warner bros", "sony pictures", "espn", "official",
}
MOOD_QUERIES = {
    "dark_hype": "dark hype viral edit song slowed reverb",
    "epic_cinematic": "epic cinematic edit audio",
    "emotional_romance": "emotional romance edit song",
    "cold_sigma": "cold sigma edit song slowed",
}

def rapid_keys():
    return [os.environ.get(f"RAPIDAPI_KEY_{i}") for i in range(1, 5) if os.environ.get(f"RAPIDAPI_KEY_{i}")]

def is_blacklisted(title: str, channel: str) -> bool:
    t = (title + " " + channel).lower()
    return any(b in t for b in BLACKLIST)

def search_clean(query: str, max_results: int = 8) -> list[dict]:
    """Stub: returns empty if no RapidAPI. Full version calls RapidAPI YouTube search."""
    keys = rapid_keys()
    if not keys:
        return []
    # Placeholder — real impl uses requests to youtube-info-download-api or similar
    return []

def pick_song(mood: str, songs_bank_dir: Path) -> Path | None:
    """Try local songs-bank first, else return None (caller can RapidAPI fallback)."""
    if not songs_bank_dir.exists():
        return None
    # simple mood folder or filename match
    for p in songs_bank_dir.glob("*.mp3"):
        if mood.split("_")[0] in p.name.lower():
            return p
    mp3s = list(songs_bank_dir.glob("*.mp3"))
    return mp3s[0] if mp3s else None

def download_yt(url: str, out: Path) -> bool:
    """Stub download. Real version uses RapidAPI or yt-dlp."""
    return False
