"""Sourcing with verbose yt-dlp fallback."""
from __future__ import annotations
import base64, os, subprocess, tempfile
from pathlib import Path

BLACKLIST = {"netflix", "crunchyroll", "prime video", "amazon prime", "hbo", "disney+", "marvel entertainment", "warner bros", "sony pictures", "espn"}

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
    print("YT-DLP trying:", query[:60])
    search_cmd = [
        "yt-dlp", "--no-playlist", "--skip-download",
        "--print", "%(id)s|||%(title)s|||%(channel)s",
        f"ytsearch6:{query}",
    ] + ytdlp_cookie_args()
    r = subprocess.run(search_cmd, capture_output=True, text=True, timeout=90)
    print("search rc", r.returncode, "stdout lines", len((r.stdout or "").splitlines()))
    if r.returncode != 0:
        print("search err", (r.stderr or "")[-300:])
    for line in (r.stdout or "").splitlines():
        parts = line.split("|||")
        if len(parts) < 3:
            continue
        vid, title, channel = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if is_blacklisted(title, channel):
            print("skip blacklist", title[:40])
            continue
        print("trying", vid, title[:50])
        dl_cmd = [
            "yt-dlp", "--no-playlist",
            "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
            "--extractor-args", "youtube:player_client=android,web",
            "-o", str(out),
            f"https://www.youtube.com/watch?v={vid}",
        ] + ytdlp_cookie_args()
        d = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=240)
        if d.returncode == 0 and out.exists() and out.stat().st_size > 100_000:
            print("DOWNLOADED", out.stat().st_size)
            return {"title": title, "channel": channel, "id": vid, "path": str(out)}
        else:
            print("dl fail", (d.stderr or "")[-200:])
    return None

def search_and_download(query: str, out: Path) -> dict | None:
    # Direct yt-dlp (RapidAPI endpoint unreliable for full download)
    return ytdlp_download(query, out)

def pick_or_download_song(mood: str, songs_dir: Path, out: Path) -> Path | None:
    if songs_dir.exists():
        for p in songs_dir.glob("*.mp3"):
            if mood.split("_")[0] in p.name.lower():
                return p
        mp3s = list(songs_dir.glob("*.mp3"))
        if mp3s:
            return mp3s[0]
    return None
