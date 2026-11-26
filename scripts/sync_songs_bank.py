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
import time
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


def _score(v: dict, title: str, artist: str) -> int:
    t = v["title"].lower()
    ch = (v.get("channel") or "").lower()
    d = v.get("duration") or 0
    if d and not (90 <= d <= 600):          # unknown length (0) is allowed: download caps at 10 min
        return -1
    if any(b in t for b in BAD) and not any(b in title.lower() for b in BAD):
        return -1
    score = 0
    if title.lower().split("(")[0].strip()[:12] in t:
        score += 3
    if artist.lower().split(",")[0].split("&")[0].strip()[:10] in (t + " " + ch):
        score += 2
    if "official" in t or "topic" in ch or "vevo" in ch or "records" in ch:
        score += 1
    return score


def pick_video(title: str, artist: str) -> dict | None:
    """Only the original: title must match AND (artist channel/title or official / Topic / VEVO / label upload).
    Tries 3 query phrasings; each search retried once on a transient error."""
    best = None
    for q in (f"{title} {artist} official audio", f"{artist} - {title}", f"{title} {artist} topic"):
        res = []
        for attempt in range(2):
            try:
                res = rapid_search(q)
                break
            except AllKeysExhausted:
                raise
            except RapidAPIError as e:
                print("  search retry:", str(e)[:120])
                time.sleep(3)
        for v in res:
            sc = _score(v, title, artist)
            if sc >= 4 and (best is None or sc > best[0]):
                best = (sc, v)
        if best and best[0] >= 5:
            break
    return best[1] if best else None


def tag_song(path: Path, mood: str) -> dict | None:
    """BPM / drop / loudness tag (same as scripts/tag_songs.py) so runs don't spend time tagging."""
    try:
        from pipeline_lib import song_mood as SM
        from pipeline_lib.audio_sync import detect_beats
        b = detect_beats(path)
        return SM.tag_entry(mood, b.get("tempo") or 0, None, b.get("drop"))
    except Exception as e:
        print("  tag skipped:", type(e).__name__)
        return None


PRIORITY = ("romance", "hype", "aggressive", "emotional", "epic", "dark")


def main():
    if not rapid_available():
        print("ERROR: no YT_RAPIDAPI_KEY_1..4 / RAPIDAPI_KEY_1..4 in env")
        sys.exit(1)
    from pipeline_lib import song_mood as SM
    catalog = json.loads(CATALOG.read_text())["songs"]
    catalog.sort(key=lambda s: (PRIORITY.index(s["mood"]) if s["mood"] in PRIORITY else 99,
                                int(s["file"].rsplit("_", 1)[-1].split(".")[0] or 0)))
    if run(["gh", "release", "view", RELEASE, "--repo", REPO], timeout=20).returncode != 0:
        run(["gh", "release", "create", RELEASE, "--repo", REPO,
             "--title", "RIYIO songs-bank", "--notes", "Mood-matched songs for the pipeline"], timeout=30)
    have = existing_assets()
    print(f"songs-bank currently has {len(have)} assets")
    limit = int(os.environ.get("SYNC_LIMIT", "0") or 0)
    budget = float(os.environ.get("SYNC_BUDGET_MIN", "300") or 300) * 60
    t0 = time.time()
    tags = SM.load_tags()
    ok = fail = 0
    failed = []
    for s in catalog:
        name = s["file"]
        if name in have:
            continue
        if limit and ok >= limit:
            break
        if time.time() - t0 > budget:
            print("BUDGET reached - re-run sync-songs-bank to continue (already uploaded songs are skipped)")
            break
        tmp = Path("/tmp") / name
        print(f"fetching {name} — {s['title']} – {s['artist']}")
        try:
            v = pick_video(s["title"], s["artist"])
            if not v:
                print("  no suitable search result")
                fail += 1
                failed.append(name)
                continue
            print(f"  -> {v['title'][:70]} | {v.get('channel', '')[:30]} ({int(v.get('duration') or 0)}s)")
            for attempt in range(2):
                try:
                    rapid_download(v["url"], tmp, fmt="mp3", max_minutes=10)
                    break
                except AllKeysExhausted:
                    raise
                except RapidAPIError as e:
                    if attempt:
                        raise
                    print("  download retry:", str(e)[:120])
                    time.sleep(5)
            if not tmp.exists() or tmp.stat().st_size < 500_000:
                print("  FAILED: file too small")
                fail += 1
                failed.append(name)
                tmp.unlink(missing_ok=True)
                continue
        except AllKeysExhausted as e:
            print("STOP:", e)
            break
        except RapidAPIError as e:
            print("  FAILED:", str(e)[:200])
            fail += 1
            failed.append(name)
            continue
        up = None
        for attempt in range(3):
            up = run(["gh", "release", "upload", RELEASE, str(tmp), "--repo", REPO, "--clobber"], timeout=240)
            if up.returncode == 0:
                break
            time.sleep(5 * (attempt + 1))
        if up.returncode == 0:
            ok += 1
            print("  uploaded", name)
            tg = tag_song(tmp, s["mood"])
            if tg:
                tags[name] = tg
                SM.save_tags(tags)
        else:
            fail += 1
            failed.append(name)
        tmp.unlink(missing_ok=True)
    have = existing_assets()
    by = {}
    for s in catalog:
        if s["file"] in have:
            by[s["mood"]] = by.get(s["mood"], 0) + 1
    print(f"DONE — uploaded {ok} new songs, {fail} failed, songs-bank total = {len(have)}")
    print("PER MOOD", json.dumps(by, sort_keys=True))
    if failed:
        print("FAILED SONGS", failed)
    if not have:
        sys.exit(1)


if __name__ == "__main__":
    main()
