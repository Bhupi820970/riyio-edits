"""Working RapidAPI downloader (exact pre-v2 endpoints). No yt-dlp."""
from __future__ import annotations
import json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

RAPID_HOST = "youtube-info-download-api.p.rapidapi.com"
RAPID_BASE = f"https://{RAPID_HOST}"
UA = "Mozilla/5.0 (X11; Linux x86_64) riyio-pipeline/1.0"
BLACKLIST = {"netflix", "crunchyroll", "prime video", "amazon prime", "hbo", "disney+", "marvel entertainment", "warner bros", "sony pictures", "espn"}

class RapidAPIError(RuntimeError):
    pass

def _keys() -> list[tuple[int, str]]:
    out = []
    for i in range(1, 5):
        # support both old YT_RAPIDAPI_KEY_ and new RAPIDAPI_KEY_
        k = (os.environ.get(f"YT_RAPIDAPI_KEY_{i}") or os.environ.get(f"RAPIDAPI_KEY_{i}") or "").strip()
        if k:
            out.append((i, k))
    return out

_DEAD = set()
_CUR = 0

def _rapid_get(path: str, params: dict, timeout: int = 60) -> dict:
    global _CUR
    keys = _keys()
    if not keys:
        raise RapidAPIError("no RapidAPI keys")
    qs = urllib.parse.urlencode(params)
    url = f"{RAPID_BASE}{path}?{qs}"
    n = len(keys)
    for step in range(n):
        slot, key = keys[(_CUR + step) % n]
        if slot in _DEAD:
            continue
        req = urllib.request.Request(url, headers={
            "x-rapidapi-host": RAPID_HOST, "x-rapidapi-key": key, "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", errors="ignore") or "{}")
            _CUR = (_CUR + step) % n
            return data
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                _DEAD.add(slot)
                continue
            raise RapidAPIError(f"http {e.code}") from e
    raise RapidAPIError("all keys exhausted")

def is_blacklisted(title: str, channel: str) -> bool:
    t = (title + " " + channel).lower()
    return any(b in t for b in BLACKLIST)

def rapid_search(query: str) -> list[dict]:
    data = _rapid_get("/api/youtube/search", {"q": query})
    vids = data.get("videos") or data.get("results") or data.get("items") or []
    out = []
    for v in vids:
        if not isinstance(v, dict):
            continue
        vid = v.get("id") or v.get("videoId") or ""
        link = v.get("link") or v.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        if not link:
            continue
        ch = v.get("channel")
        if isinstance(ch, dict):
            ch = ch.get("name") or ""
        out.append({"id": vid, "title": v.get("title") or "", "url": link, "channel": ch or ""})
    return out

def rapid_download(url: str, out: Path, fmt: str = "mp4") -> dict:
    params = {"url": url, "format": fmt, "max_duration": "12"}
    if fmt == "mp3":
        params["audio_quality"] = "192"
    job = _rapid_get("/ajax/download.php", params)
    if not job.get("success"):
        raise RapidAPIError(f"start failed: {job}")
    progress = job.get("progress_url")
    if not progress:
        raise RapidAPIError("no progress_url")
    dl = None
    for _ in range(60):
        time.sleep(5)
        try:
            with urllib.request.urlopen(progress, timeout=30) as r:
                p = json.loads(r.read().decode() or "{}")
        except Exception:
            continue
        if int(p.get("progress") or 0) >= 1000 and p.get("download_url"):
            dl = p["download_url"]
            break
    if not dl:
        raise RapidAPIError("conversion timeout")
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-fsSL", "--retry", "3", "-A", UA, "-o", str(out), dl],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 50_000:
        raise RapidAPIError("file fetch failed")
    return {"title": job.get("title") or "", "id": job.get("id") or "", "path": str(out)}

def search_and_download(query: str, out: Path) -> dict | None:
    print("RapidAPI search:", query[:50])
    try:
        results = rapid_search(query)
    except Exception as e:
        print("search fail", e)
        return None
    print("got", len(results), "results")
    for it in results[:6]:
        if is_blacklisted(it["title"], it["channel"]):
            print("skip", it["title"][:40])
            continue
        try:
            info = rapid_download(it["url"], out)
            info["title"] = it["title"]
            info["channel"] = it["channel"]
            print("DOWNLOADED", out.stat().st_size)
            return info
        except Exception as e:
            print("dl fail", e)
            continue
    return None

def pick_or_download_song(mood: str, songs_dir: Path, out: Path) -> Path | None:
    if songs_dir.exists():
        for p in songs_dir.glob("*.mp3"):
            if mood.split("_")[0] in p.name.lower():
                return p
        mp3s = list(songs_dir.glob("*.mp3"))
        if mp3s:
            return mp3s[0]
    return None
