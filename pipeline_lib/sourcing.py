"""Real RapidAPI download + songs-bank / RapidAPI song fallback."""
from __future__ import annotations
import os, subprocess, requests
from pathlib import Path

BLACKLIST = {"netflix", "crunchyroll", "prime video", "amazon prime", "hbo", "disney+", "marvel entertainment", "warner bros", "sony pictures", "espn"}
MOOD_QUERIES = {
    "dark_hype": "dark hype viral edit song slowed reverb",
    "epic_cinematic": "epic cinematic edit audio",
    "emotional_romance": "emotional romance edit song",
    "cold_sigma": "cold sigma edit song slowed",
}

def keys():
    return [os.environ.get(f"RAPIDAPI_KEY_{i}") for i in range(1, 5) if os.environ.get(f"RAPIDAPI_KEY_{i}")]

def is_blacklisted(title: str, channel: str) -> bool:
    t = (title + " " + channel).lower()
    return any(b in t for b in BLACKLIST)

def search_and_download(query: str, out: Path, max_try: int = 4) -> dict | None:
    """Search via RapidAPI and download first non-blacklisted video."""
    ks = keys()
    if not ks:
        return None
    host = "youtube-info-download-api.p.rapidapi.com"
    for k in ks:
        try:
            r = requests.get(
                f"https://{host}/search",
                headers={"x-rapidapi-key": k, "x-rapidapi-host": host},
                params={"query": query, "type": "video"},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            items = r.json().get("items") or r.json().get("results") or []
            for it in items[:max_try]:
                title = it.get("title") or ""
                channel = it.get("channel") or it.get("author") or ""
                vid = it.get("id") or it.get("videoId")
                if not vid or is_blacklisted(title, channel):
                    continue
                # download
                dr = requests.get(
                    f"https://{host}/download",
                    headers={"x-rapidapi-key": k, "x-rapidapi-host": host},
                    params={"id": vid, "format": "mp4"},
                    timeout=120,
                    stream=True,
                )
                if dr.status_code == 200 and int(dr.headers.get("content-length", 0)) > 100_000:
                    out.write_bytes(dr.content)
                    return {"title": title, "channel": channel, "id": vid, "path": str(out)}
        except Exception:
            continue
    return None

def pick_or_download_song(mood: str, songs_dir: Path, out: Path) -> Path | None:
    """songs-bank first, else RapidAPI search for mood track."""
    if songs_dir.exists():
        for p in songs_dir.glob("*.mp3"):
            if mood.split("_")[0] in p.name.lower():
                return p
        mp3s = list(songs_dir.glob("*.mp3"))
        if mp3s:
            return mp3s[0]
    # fallback RapidAPI (stub-safe)
    info = search_and_download(MOOD_QUERIES.get(mood, "cinematic edit audio"), out)
    return Path(info["path"]) if info else None
