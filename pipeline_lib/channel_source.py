"""channels/channels.txt -> candidate videos from trusted channels (yt-dlp flat listing, metadata only;
the download itself still goes through the RapidAPI downloader)."""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNELS = ROOT / "channels" / "channels.txt"
SKIP = ("trailer", "teaser", "featurette", "interview", "behind the scenes", "review", "reaction", "#shorts",
        "every ", "compilation", "trilogy:", "all ", "top 10", "ranking", "explained", "bloopers", "deleted scene")


def channel_urls() -> list[str]:
    if not CHANNELS.exists():
        return []
    out = []
    for ln in CHANNELS.read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "youtube.com/" in ln:
            out.append(ln.rstrip("/"))
    return out


def list_videos(channel_url: str, limit: int = 60) -> tuple[str, list[dict]]:
    url = channel_url if channel_url.endswith("/videos") else channel_url + "/videos"
    r = subprocess.run(["yt-dlp", "--flat-playlist", "--playlist-end", str(limit), "-J", url],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print("channel listing failed:", channel_url, (r.stderr or "")[-200:], flush=True)
        return "", []
    d = json.loads(r.stdout or "{}")
    name = d.get("channel") or d.get("uploader") or channel_url
    vids = []
    for e in d.get("entries") or []:
        if e.get("id"):
            vids.append({"id": e["id"], "title": e.get("title") or "", "duration": e.get("duration") or 0,
                         "views": e.get("view_count") or 0, "channel": name,
                         "url": f"https://www.youtube.com/watch?v={e['id']}"})
    return name, vids


def score(v: dict) -> float:
    t = v["title"].lower()
    if any(k in t for k in SKIP):
        return -1
    if not (90 <= (v["duration"] or 0) <= 720):
        return -1
    s = 1.0
    if re.search(r"[\"“”]", v["title"]):  # quoted line = dialogue moment
        s += 2
    if "scene" in t or "clip" in t:
        s += 1
    if "4k" in t:
        s += 1
    return s + min(3.0, (v["views"] or 0) / 50000)


def candidates(skip_ids: set[str], per_channel: int = 4) -> list[dict]:
    from pipeline_lib import channel_blocklist
    out = []
    for cu in channel_urls():
        try:
            name, vids = list_videos(cu)
        except Exception as e:
            print("channel listing error:", cu, repr(e)[:150], flush=True)
            continue
        if channel_blocklist.is_blocked(name):
            print("channel on learned blocklist, skipped:", name, flush=True)
            continue
        good = [v for v in vids if v["id"] not in skip_ids and score(v) > 0]
        good.sort(key=score, reverse=True)
        print(f"CHANNEL {name}: {len(vids)} listed, {len(good)} usable", flush=True)
        out += good[:per_channel]
    return out
