"""Sourcing: RapidAPI attempt + yt-dlp fallback. Blacklist intact."""
from __future__ import annotations
import base64, json, os, subprocess, tempfile
from pathlib import Path

import requests

BLACKLIST = {"netflix", "crunchyroll", "prime video", "amazon prime", "hbo", "disney+", "marvel entertainment", "warner bros", "sony pictures", "espn"}
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

def ytdlp_cookie_args() -> list[str]:
    cookies = (os.environ.get("YT_COOKIES") or "").strip()
    if not cookies:
        return []
    try:
        if not cookies.startswith("#") and "\t" not in cookies[:120]:
            cookies = base64.b64decode(cookies).decode("utf-8", errors="ignore")
        if not cookies.startswith("# Netscape"):
            cookies = "# Netscape HTTP Cookie File\n" + cookies
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="ytc_")
        os.write(fd, cookies.encode())
        os.close(fd)
        return ["--cookies", path]
    except Exception:
        return []

def ytdlp_download(query: str, out: Path) -> dict | None:
    """yt-dlp search + download with blacklist check."""
    cmd = [
        "yt-dlp", "--no-playlist", "-f", "bv*+ba/b",
        "--extractor-args", "youtube:player_client=android,web",
        "--print", "%(id)s\t%(title)s\t%(channel)s",
        f"ytsearch8:{query}",
    ] + ytdlp_cookie_args()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        vid, title, channel = parts[0], parts[1], parts[2]
        if is_blacklisted(title, channel):
            continue
        dl = [
            "yt-dlp", "--no-playlist", "-f", "bv*+ba/b",
            "--extractor-args", "youtube:player_client=android,web",
            "-o", str(out), f"https://www.youtube.com/watch?v={vid}",
        ] + ytdlp_cookie_args()
        d = subprocess.run(dl, capture_output=True, text=True, timeout=180)
        if d.returncode == 0 and out.exists() and out.stat().st_size > 200_000:
            return {"title": title, "channel": channel, "id": vid, "path": str(out)}
    return None

def search_and_download(query: str, out: Path) -> dict | None:
    """Try RapidAPI first, fall back to yt-dlp."""
    # RapidAPI attempt (best-effort)
    ks = rapid_keys()
    if ks:
        host = "youtube-info-download-api.p.rapidapi.com"
        for k in ks[:2]:
            try:
                r = requests.get(
                    f"https://{host}/search",
                    headers={"x-rapidapi-key": k, "x-rapidapi-host": host},
                    params={"query": query},
                    timeout=20,
                )
                if r.status_code == 200:
                    items = r.json().get("items") or r.json().get("results") or []
                    for it in items[:4]:
                        title = it.get("title") or ""
                        channel = it.get("channel") or it.get("author") or ""
                        vid = it.get("id") or it.get("videoId")
                        if vid and not is_blacklisted(title, channel):
                            # try direct download via yt-dlp with the id
                            info = ytdlp_download(f"https://www.youtube.com/watch?v={vid}", out)
                            if info:
                                info["title"] = title
                                info["channel"] = channel
                                return info
            except Exception:
                pass
    # yt-dlp search fallback
    return ytdlp_download(query, out)

def pick_or_download_song(mood: str, songs_dir: Path, out: Path) -> Path | None:
    if songs_dir.exists():
        for p in songs_dir.glob("*.mp3"):
            if mood.split("_")[0] in p.name.lower():
                return p
        mp3s = list(songs_dir.glob("*.mp3"))
        if mp3s:
            return mp3s[0]
    # yt-dlp audio fallback
    info = ytdlp_download(MOOD_QUERIES.get(mood, "cinematic edit audio"), out)
    return Path(info["path"]) if info else None
