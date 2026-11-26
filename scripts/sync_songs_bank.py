#!/usr/bin/env python3
"""Sync missing catalog songs into the songs-bank GitHub Release.

Downloads MP3s via RapidAPI (youtube-info-download-api) with automatic key
rotation across YT_RAPIDAPI_KEY_1..4. Does NOT commit mp3s into git — only
uploads to the release. Key values are never printed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline_lib.sourcing import (  # noqa: E402
    AllKeysExhausted, RapidAPIError, rapid_available, rapid_download, rapid_search,
)

CATALOG = Path("config/songs_catalog.json")
REPO = os.environ.get("REPO", "Bhupi820970/riyio-edits")
RELEASE = "songs-bank"
BAD = ("live", "cover", "remix", "karaoke", "reaction", "8d", "slowed", "sped up",
       "nightcore", "instrumental version", "1 hour", "10 hours", "loop", "tribute", "type beat",
       "bass boosted", "reverb", "extended", "fan made")


def run(cmd, timeout=300):
    print("+", " ".join(cmd[:6]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print((r.stderr or "")[-400:])
    return r


def existing_assets() -> set[str]:
    r = run(["gh", "release", "view", RELEASE, "--repo", REPO, "--json", "assets"], timeout=30)
    if r.returncode != 0:
        return set()
    try:
        return {a["name"] for a in json.loads(r.stdout).get("assets", [])}
    except Exception:
        return set()


def pick_video(title: str, artist: str) -> dict | None:
    q = f"{title} {artist} official audio"
    res = rapid_search(q)
    good = []
    for v in res:
        t = v["title"].lower()
        d = v.get("duration") or 0
        if d and not (90 <= d <= 600):          # unknown length (0) is allowed: download caps at 10 min
            continue
        if any(b in t for b in BAD) and not any(b in title.lower() for b in BAD):
            continue
        score = 0
        if title.lower().split("(")[0].strip()[:12] in t:
            score += 3
        if artist.lower().split(",")[0].split("&")[0].strip()[:10] in (t + " " + v["channel"].lower()):
            score += 2
        if "official" in t or "topic" in v["channel"].lower() or "vevo" in v["channel"].lower():
            score += 1
        good.append((score, v))
    # only the original: title must match AND (artist channel/title or official / Topic / VEVO upload)
    good = [g for g in good if g[0] >= 4]
    if not good:
        return None
    good.sort(key=lambda x: -x[0])
    return good[0][1]


def main():
    if not rapid_available():
        print("ERROR: no YT_RAPIDAPI_KEY_1..4 in env")
        sys.exit(1)
    catalog = json.loads(CATALOG.read_text())["songs"]
    if run(["gh", "release", "view", RELEASE, "--repo", REPO], timeout=20).returncode != 0:
        run(["gh", "release", "create", RELEASE, "--repo", REPO,
             "--title", "RIYIO songs-bank", "--notes", "Mood-matched songs for the pipeline"], timeout=30)
    have = existing_assets()
    print(f"songs-bank currently has {len(have)} assets")
    limit = int(os.environ.get("SYNC_LIMIT", "0") or 0)
    ok = fail = 0
    for s in catalog:
        name = s["file"]
        if name in have:
            continue
        if limit and ok >= limit:
            break
        tmp = Path("/tmp") / name
        print(f"fetching {name} — {s['title']} – {s['artist']}")
        try:
            v = pick_video(s["title"], s["artist"])
            if not v:
                print("  no suitable search result")
                fail += 1
                continue
            print(f"  -> {v['title'][:70]} ({int(v['duration'])}s)")
            rapid_download(v["url"], tmp, fmt="mp3", max_minutes=10)
            if not tmp.exists() or tmp.stat().st_size < 500_000:
                print("  FAILED: file too small")
                fail += 1
                tmp.unlink(missing_ok=True)
                continue
        except AllKeysExhausted as e:
            print("STOP:", e)
            break
        except RapidAPIError as e:
            print("  FAILED:", str(e)[:200])
            fail += 1
            continue
        r = run(["gh", "release", "upload", RELEASE, str(tmp), "--repo", REPO, "--clobber"], timeout=180)
        if r.returncode == 0:
            ok += 1
            print("  uploaded", name)
        else:
            fail += 1
        tmp.unlink(missing_ok=True)
    total = len(existing_assets())
    print(f"DONE — uploaded {ok} new songs, {fail} failed, songs-bank total = {total}")
    if total == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
