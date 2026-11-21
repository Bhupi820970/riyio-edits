"""Sourcing helpers: RapidAPI YouTube downloads (key rotation), search queries,
song bank, clean-content vetting.

RapidAPI host: youtube-info-download-api.p.rapidapi.com
  GET /api/youtube/search?q=...                -> {"videos": [{id,title,link,channel,duration,...}]}
  GET /ajax/download.php?url=...&format=...    -> {"success": true, "id", "progress_url", "title"}
  GET progress_url (free, no key)              -> {"progress": 0..1000, "success": 0|1, "download_url"}

Keys come ONLY from env YT_RAPIDAPI_KEY_1..4 (GitHub secrets). Key values are
never printed; logs refer to keys by slot number only.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CATALOG_PATH = Path("config/songs_catalog.json")
RAPID_HOST = "youtube-info-download-api.p.rapidapi.com"
RAPID_BASE = f"https://{RAPID_HOST}"
UA = "Mozilla/5.0 (X11; Linux x86_64) riyio-pipeline/1.0"

# Clip length rules: never loop tiny fragments.
MIN_CLIP_S = 20.0
MAX_CLIP_SEARCH_S = 600.0

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

# Titles that almost always mean overlays / face-cams / scoreboards / logos.
BAD_TITLE_WORDS = (
    "reaction", "reacts", "reacting", "react ", "livestream", "live stream", "twitch",
    "stream highlights", "podcast", "facecam", "face cam", "commentary", "let's play",
    "lets play", "walkthrough", "playthrough", "full match", "scoreboard", "watch along",
    "watchalong", "review", "explained", "breakdown", "tiktok compilation", "meme",
    "shorts compilation", "#shorts", "fan cam", "fancam", "lyric", "lyrics",
)


# ---------------------------------------------------------------- RapidAPI
class RapidAPIError(RuntimeError):
    pass


class AllKeysExhausted(RapidAPIError):
    pass


def _rapid_keys() -> list[tuple[int, str]]:
    keys = []
    for i in range(1, 5):
        k = (os.environ.get(f"YT_RAPIDAPI_KEY_{i}") or "").strip()
        if k:
            keys.append((i, k))
    return keys


_DEAD_SLOTS: set[int] = set()
_CUR = 0


def rapid_available() -> bool:
    return bool(_rapid_keys())


def _is_rotate_error(code: int, body: str) -> bool:
    b = body.lower()
    if code in (401, 403, 429):
        return True
    return any(x in b for x in ("rate limit", "rate-limit", "too many requests", "quota",
                                 "exceeded", "not subscribed", "invalid api key",
                                 "upgrade your plan"))


def rapid_get(path: str, params: dict, timeout: int = 60) -> dict:
    """GET a RapidAPI endpoint, rotating keys 1..4 on 401/403/429/quota errors.

    Raises AllKeysExhausted only when every key has failed with a rotate error.
    """
    global _CUR
    keys = _rapid_keys()
    if not keys:
        raise AllKeysExhausted("no YT_RAPIDAPI_KEY_1..4 in env")
    qs = urllib.parse.urlencode(params)
    url = f"{RAPID_BASE}{path}?{qs}"
    last = ""
    n = len(keys)
    for step in range(n):
        slot, key = keys[(_CUR + step) % n]
        if slot in _DEAD_SLOTS:
            continue
        req = urllib.request.Request(url, headers={
            "x-rapidapi-host": RAPID_HOST, "x-rapidapi-key": key, "User-Agent": UA})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read().decode("utf-8", errors="ignore")
                data = json.loads(body or "{}")
                msg = str(data.get("message") or data.get("error") or "") if isinstance(data, dict) else ""
                if isinstance(data, dict) and msg and _is_rotate_error(200, msg) and not data.get("videos"):
                    raise urllib.error.HTTPError(url, 429, msg, None, None)  # type: ignore[arg-type]
                _CUR = (_CUR + step) % n
                return data
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="ignore")[:300] if e.fp else str(e.msg)
                except Exception:
                    body = str(e.msg)
                if _is_rotate_error(e.code, body):
                    print(f"[rapidapi] key slot {slot} -> {e.code}, rotating")
                    _DEAD_SLOTS.add(slot)
                    last = f"{e.code} {body[:120]}"
                    break
                if e.code >= 500 and attempt == 0:
                    time.sleep(3)
                    continue
                raise RapidAPIError(f"{path} http {e.code}: {body[:200]}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == 0:
                    time.sleep(3)
                    continue
                raise RapidAPIError(f"{path} network error: {e}") from e
    raise AllKeysExhausted(f"all RapidAPI keys exhausted ({last})")


def rapid_search(query: str) -> list[dict]:
    """Search YouTube. Returns list of {id,title,url,channel,duration(s)}."""
    data = rapid_get("/api/youtube/search", {"q": query})
    vids = data.get("videos") or data.get("results") or data.get("items") or []
    out = []
    for v in vids:
        if not isinstance(v, dict):
            continue
        vid = v.get("id") or v.get("videoId") or ""
        link = v.get("link") or v.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        if not link:
            continue
        dur = v.get("duration")
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            dur = _parse_dur(str(v.get("durationString") or dur or ""))
        ch = v.get("channel")
        if isinstance(ch, dict):
            ch = ch.get("name") or ch.get("title") or ""
        out.append({"id": vid, "title": v.get("title") or "", "url": link,
                    "channel": ch or "", "duration": dur or 0.0})
    return out


def _parse_dur(s: str) -> float:
    parts = [p for p in re.split(r"[:]", s.strip()) if p.isdigit()]
    if not parts:
        return 0.0
    tot = 0
    for p in parts:
        tot = tot * 60 + int(p)
    return float(tot)


def rapid_download(url: str, fmt: str, out: Path, *, start: float | None = None,
                   end: float | None = None, max_minutes: int = 12,
                   poll_timeout: int = 600) -> dict:
    """Start a RapidAPI conversion job, poll progress_url, save file to `out`."""
    params = {"url": url, "format": fmt, "max_duration": str(max_minutes)}
    if fmt == "mp3":
        params["audio_quality"] = "192"
    if start is not None:
        params["start_time"] = str(int(start))
    if end is not None:
        params["end_time"] = str(int(end))
    job = rapid_get("/ajax/download.php", params)
    if not job.get("success") or not job.get("progress_url"):
        raise RapidAPIError(f"download start failed: {str(job.get('message') or job)[:200]}")
    purl = job["progress_url"]
    deadline = time.time() + poll_timeout
    dl = ""
    while time.time() < deadline:
        time.sleep(2)
        try:
            req = urllib.request.Request(purl, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                p = json.loads(r.read().decode("utf-8", errors="ignore") or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 503:
                continue
            raise RapidAPIError(f"progress http {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        prog = int(float(p.get("progress") or 0))
        if prog >= 1000:
            if int(p.get("success") or 0) == 1 and p.get("download_url"):
                dl = p["download_url"]
                break
            raise RapidAPIError(f"conversion failed: {p.get('message') or p.get('text')}")
    if not dl:
        raise RapidAPIError("conversion timed out")
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-fsSL", "--retry", "3", "-A", UA, "-o", str(out), dl],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 50_000:
        raise RapidAPIError(f"file fetch failed ({r.returncode})")
    return {"title": job.get("title") or "", "id": job.get("id") or "", "path": out}


def youtube_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- legacy yt-dlp (non-YouTube links e.g. X)
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


# ---------------------------------------------------------------- queries
def clean_topic(topic: str) -> str:
    """Strip queue noise (random numbers, ids) from a topic."""
    t = re.sub(r"\b[a-z]+_\d+_\d+\b", " ", topic or "", flags=re.I)
    t = re.sub(r"\b\d{2,}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def search_queries_for(genre: str, topic: str) -> list[str]:
    t = clean_topic(topic) or f"{genre} cinematic scene"
    # Prioritize specific movie/series scene searches for cohesive sourcing
    return [
        f"{t} best scenes",
        f"{t} official clip",
        f"{t} movie scene 4k",
        f"best {t} dialogue scenes",
        f"{t} film clip no watermark",
        f"{genre} {t} cinematic scene",
    ]


def title_is_clean(title: str, channel: str = "") -> tuple[bool, str]:
    t = f" {title} {channel} ".lower()
    for w in BAD_TITLE_WORDS:
        if w in t:
            return False, f"title has '{w.strip()}'"
    return True, "ok"


# ---------------------------------------------------------------- clean-content vetting
VET_PROMPT = """You are a strict content filter for a cinematic fan-edit channel.
Look at these frames from ONE video clip. Reject the clip if ANY frame shows:
- a watermark or channel/TV/network logo (any corner or overlay text branding)
- a face-cam / webcam bubble / streamer picture-in-picture
- a streamer overlay (chat box, alerts, donation bar, subscriber goal, HUD of a stream)
- a sports scoreboard / score bug / ticker / broadcast graphics
- burned-in social media UI (TikTok/Instagram/X username, like buttons), big meme text
Normal film/game scenes, letterbox bars, and small built-in game HUD are OK.
Reply JSON only: {"accept": true|false, "issues": ["..."], "reason": "short"}"""


def _shrink_b64(b64: str, width: int = 640) -> str:
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        if im.width > width:
            im = im.resize((width, int(im.height * width / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return b64


def static_overlay_check(video: Path, samples: int = 10) -> tuple[bool, str]:
    """Fallback (no Groq): detect static logos / face-cam boxes / scoreboards.

    A region that stays pixel-identical across the clip while containing sharp
    edges = burned-in overlay. Letterbox bars are flat (no edges) so they pass.
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return True, "opencv missing — heuristic skipped"
    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n < samples * 3:
        cap.release()
        return True, "too few frames for heuristic"
    frames = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / samples))
        ok, fr = cap.read()
        if ok:
            fr = cv2.resize(fr, (480, 270))
            frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()
    if len(frames) < 4:
        return True, "could not sample frames"
    st = np.stack(frames)
    std = st.std(axis=0)
    med = np.median(st, axis=0).astype(np.uint8)
    edges = cv2.Canny(med, 80, 180) > 0
    static_edges = edges & (std < 3.0)
    # scene must actually move, else everything looks static
    if float(np.mean(std)) < 6.0:
        return True, "low-motion clip — heuristic inconclusive"
    h, w = static_edges.shape
    regions = {
        "top-left": static_edges[: h // 5, : w // 4],
        "top-right": static_edges[: h // 5, -w // 4:],
        "bottom-left": static_edges[-h // 5:, : w // 4],
        "bottom-right": static_edges[-h // 5:, -w // 4:],
        "top-band": static_edges[: h // 8, :],
        "bottom-band": static_edges[-h // 8:, :],
    }
    bad = [k for k, r in regions.items() if float(r.mean()) > 0.035]
    if bad:
        return False, "static overlay (logo/face-cam/scoreboard) in " + ",".join(bad)
    return True, "no static overlay"


def vet_keyframes_with_groq(frames: list[str], title: str = "", channel: str = "",
                            video: Path | None = None) -> dict:
    """Reject watermarks, face-cams, corner logos, scoreboards, streamer overlays.

    Primary: Groq vision (GROQ_API_KEY_1..4 rotation). Fallback: title rules +
    static-overlay pixel heuristic. Returns {"accept": bool, "reason": str}.
    """
    ok, why = title_is_clean(title, channel)
    if not ok:
        return {"accept": False, "reason": why, "by": "title"}
    from .groq_client import available as groq_available, chat as groq_chat
    if frames and groq_available():
        content = [{"type": "text", "text": VET_PROMPT + f"\nVideo title: {title[:120]}"}]
        for b in frames[:4]:
            content.append({"type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + _shrink_b64(b)}})
        raw = groq_chat([{"role": "user", "content": content}], vision=True,
                        max_tokens=200, temperature=0.0)
        if raw:
            try:
                s, e = raw.find("{"), raw.rfind("}") + 1
                data = json.loads(raw[s:e])
                acc = bool(data.get("accept"))
                reason = data.get("reason") or ", ".join(data.get("issues") or [])
                return {"accept": acc, "reason": str(reason)[:200], "by": "groq-vision"}
            except Exception:
                low = raw.lower()
                if '"accept": false' in low or "reject" in low:
                    return {"accept": False, "reason": raw[:160], "by": "groq-vision"}
    if video is not None and video.exists():
        ok, why = static_overlay_check(video)
        return {"accept": ok, "reason": why, "by": "heuristic"}
    return {"accept": True, "reason": "no vision available; title ok", "by": "title"}


# ---------------------------------------------------------------- songs
def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text()).get("songs", [])


def bank_assets(repo: str | None = None) -> set[str]:
    repo = repo or os.environ.get("REPO", "Bhupi820970/riyio-edits")
    r = subprocess.run(["gh", "release", "view", "songs-bank", "--repo", repo,
                        "--json", "assets"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return set()
    try:
        return {a["name"] for a in json.loads(r.stdout).get("assets", [])}
    except Exception:
        return set()


def pick_song_from_catalog(genre: str, used: set[str] | None = None,
                           available: set[str] | None = None) -> dict | None:
    import random
    mood = GENRE_MOOD.get(genre, "epic")
    cat = load_catalog()
    if available is not None:
        cat = [s for s in cat if s["file"] in available]
    songs = [s for s in cat if s.get("mood") == mood] or cat
    if not songs:
        return None
    used = used or set()
    fresh = [s for s in songs if s["file"] not in used] or songs
    return random.choice(fresh)


def songs_bank_url(filename: str) -> str:
    repo = os.environ.get("REPO", "Bhupi820970/riyio-edits")
    return f"https://github.com/{repo}/releases/download/songs-bank/{filename}"


def song_credit(entry: dict | None, path: Path | None = None) -> str:
    if entry and entry.get("title"):
        return f"{entry['title']} – {entry.get('artist', '')}".strip(" –")
    return path.stem if path else "Original Mix"


def ensure_song_from_bank(genre: str, dest: Path, used: set[str] | None = None) -> tuple[Path, dict]:
    """Download a mood-matched song that really exists in the songs-bank release.

    Songs-bank ONLY — there is no local/stock/dummy audio fallback.
    """
    have = bank_assets()
    if not have:
        raise RuntimeError("songs-bank release empty/missing — run sync_songs.yml first")
    entry = pick_song_from_catalog(genre, used=used, available=have)
    if not entry:
        raise RuntimeError("no catalog song present in songs-bank")
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-fsSL", "-o", str(dest), songs_bank_url(entry["file"])],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 50_000:
        raise RuntimeError(f"songs-bank download failed for {entry['file']}")
    return dest, entry
