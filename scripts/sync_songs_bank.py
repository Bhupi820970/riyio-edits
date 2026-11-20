#!/usr/bin/env python3
"""Sync missing songs from catalog to songs-bank GitHub Release.

Primary: RapidAPI YouTube (YT_RAPIDAPI_KEY_1..4 rotation).
Fallback: yt-dlp if RapidAPI fails.
Does NOT commit the mp3s into the git repo — only uploads to the release.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Make pipeline_lib importable when script is run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CATALOG = Path("config/songs_catalog.json")
REPO = os.environ.get("REPO", "Bhupi820970/riyio-edits")
RELEASE = "songs-bank"


def run(cmd, timeout=300):
    print("+", " ".join(cmd[:8]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print((r.stderr or "")[-400:])
    return r


def existing_assets() -> set[str]:
    r = run(["gh", "release", "view", RELEASE, "--repo", REPO, "--json", "assets"], timeout=30)
    if r.returncode != 0:
        return set()
    try:
        data = json.loads(r.stdout)
        return {a["name"] for a in data.get("assets", [])}
    except Exception:
        return set()


def download_one(title: str, artist: str, out: Path) -> bool:
    query = f"{title} {artist}"
    # Try RapidAPI first
    try:
        from pipeline_lib.rapidapi_yt import yt_client
        dl = yt_client.download(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}", "mp3")
        if dl:
            r = subprocess.run(["curl", "-fsSL", "-o", str(out), dl], capture_output=True)
            if r.returncode == 0 and out.exists() and out.stat().st_size > 50_000:
                return True
    except Exception as e:
        print("RapidAPI song fail:", e)

    # Fallback yt-dlp
    cmd = [
        "yt-dlp", "--no-playlist",
        "--js-runtimes", "deno",
        "--extractor-args", "youtube:player_client=tv,mweb",
        "-f", "ba/b",
        "-x", "--audio-format", "mp3", "--audio-quality", "192K",
        "-o", str(out),
        f"ytsearch1:{query}",
    ]
    cookies = os.environ.get("YT_COOKIES", "").strip()
    if cookies:
        try:
            from pipeline_lib.sourcing import ytdlp_cookie_args
            cmd += ytdlp_cookie_args()
        except Exception:
            pass
    r = run(cmd, timeout=180)
    return out.exists() and out.stat().st_size > 50_000


def main():
    catalog = json.loads(CATALOG.read_text())["songs"]
    have = existing_assets()
    print(f"songs-bank currently has {len(have)} assets")

    run(["gh", "release", "view", RELEASE, "--repo", REPO], timeout=20)
    if run(["gh", "release", "view", RELEASE, "--repo", REPO], timeout=20).returncode != 0:
        run(["gh", "release", "create", RELEASE, "--repo", REPO,
             "--title", "RIYIO songs-bank", "--notes", "Mood-matched songs for the pipeline"], timeout=30)

    ok = 0
    for s in catalog:
        name = s["file"]
        if name in have:
            print("skip", name)
            continue
        tmp = Path("/tmp") / name
        print(f"fetching {name} — {s['title']} – {s['artist']}")
        if download_one(s["title"], s["artist"], tmp):
            r = run(["gh", "release", "upload", RELEASE, str(tmp),
                     "--repo", REPO, "--clobber"], timeout=120)
            if r.returncode == 0:
                ok += 1
                print("uploaded", name)
            tmp.unlink(missing_ok=True)
        else:
            print("FAILED", name)
    print(f"DONE — uploaded {ok} new songs")


if __name__ == "__main__":
    main()
