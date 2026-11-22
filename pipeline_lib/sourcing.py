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
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")[:300]
            except Exception:
                pass
            print(f"HTTP {e.code} body: {body}")
            if e.code in (401, 403, 429):
                _DEAD.add(slot)
                continue
            raise RapidAPIError(f"http {e.code} {body}") from e
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

def rapid_download(url: str, out: Path, fmt: str = "1080") -> dict:
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

OFFICIAL_HINTS = ("official", "movieclips", "clips", "studios", "pictures", "films", "entertainment",
                  "tv", "channel", "originals", "fandango", "amc", "bbc", "fx", "a24", "lionsgate",
                  "paramount", "universal", "20th century", "focus features", "toho", "aniplex")
BAD_HINTS = ("edit", "status", "whatsapp", "tiktok", "amv", "lyrics", "reaction", "explained", "review",
             "trailer trash", "compilation", "visuals", "fan made", "fanmade", "parody", "breakdown",
             "#shorts", "shorts", "ranking", "top 10", "hindi", "dubbed in", "tamil", "telugu")


def _rank(it: dict, query: str) -> int:
    """Prefer official channel uploads of the actual scene; push fan edits/reactions down."""
    t, ch = it["title"].lower(), (it["channel"] or "").lower()
    score = 0
    if any(h in ch for h in OFFICIAL_HINTS):
        score += 3
    if "scene" in t or "clip" in t:
        score += 2
    if "4k" in t or "1080" in t or "hd" in t.split():
        score += 1
    if any(b in t or b in ch for b in BAD_HINTS):
        score -= 5
    words = [w for w in query.lower().split() if len(w) > 3 and w not in ("scene", "english")]
    score += sum(1 for w in words if w in t)
    return score


def download_bank_song(fname: str, out: Path) -> Path | None:
    """One named track from the public songs-bank release."""
    repo = os.environ.get("REPO", "Bhupi820970/riyio-edits")
    out.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repo}/releases/download/songs-bank/{fname}"
    r = subprocess.run(["curl", "-fsSL", "-L", "-o", str(out), url], capture_output=True, text=True, timeout=180)
    if r.returncode == 0 and out.exists() and out.stat().st_size >= 50_000:
        print("SONG from songs-bank", fname, out.stat().st_size, flush=True)
        return out
    out.unlink(missing_ok=True)
    return None


def search_and_download(query: str, out: Path, exclude: set | None = None) -> dict | None:
    print("RapidAPI search:", query[:50])
    try:
        results = rapid_search(query)
    except Exception as e:
        print("search fail", e)
        return None
    print("got", len(results), "results")
    results = sorted(results[:12], key=lambda it: -_rank(it, query))
    for it in results[:6]:
        if is_blacklisted(it["title"], it["channel"]):
            print("skip", it["title"][:40])
            continue
        if exclude and it["url"] in exclude:
            print("skip used", it["title"][:40])
            continue
        for fmt in ("1080", "720", "mp4", "best"):
            try:
                info = rapid_download(it["url"], out, fmt=fmt)
                info["title"] = it["title"]
                info["channel"] = it["channel"]
                info["url"] = it["url"]
                print("DOWNLOADED", fmt, out.stat().st_size)
                return info
            except Exception as e:
                print(f"dl fail {fmt}", e)
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
    try:
        got = _download_song_from_bank(mood, out)
        if got:
            return got
    except Exception as e:
        print("songs-bank fetch failed", e)
    return None


def _download_song_from_bank(mood: str, out: Path) -> Path | None:
    """Pull a mood-matched track from the public songs-bank release."""
    repo = os.environ.get("REPO", "Bhupi820970/riyio-edits")
    token = (mood or "dark").lower().replace("-", "_")
    prefixes = []
    for pref in (token, token.split("_")[0], "dark", "epic"):
        if pref and pref not in prefixes:
            prefixes.append(pref)
    candidates: list[str] = []
    catalog = Path("config/songs_catalog.json")
    if catalog.exists():
        songs = json.loads(catalog.read_text()).get("songs") or []
        for pref in prefixes:
            for s in songs:
                fname = s.get("file") or ""
                if s.get("mood") == pref or fname.startswith(pref + "_"):
                    candidates.append(fname)
        candidates.extend(s.get("file") or "" for s in songs)
    else:
        for pref in prefixes:
            candidates.extend(f"{pref}_{i}.mp3" for i in range(1, 11))
    files: list[str] = []
    for f in candidates:
        if f and f not in files:
            files.append(f)
    out.parent.mkdir(parents=True, exist_ok=True)
    for fname in files[:8]:
        url = f"https://github.com/{repo}/releases/download/songs-bank/{fname}"
        r = subprocess.run(
            ["curl", "-fsSL", "-L", "-o", str(out), url],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode == 0 and out.exists() and out.stat().st_size >= 50_000:
            print("SONG from songs-bank", fname, out.stat().st_size)
            return out
        if out.exists():
            out.unlink(missing_ok=True)
    return None
