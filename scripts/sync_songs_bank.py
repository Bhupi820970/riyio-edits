#!/usr/bin/env python3
"""Sync missing songs from catalog to songs-bank GitHub Release.

NOTE: This script is a template. Downloading copyrighted commercial tracks
and uploading them to a public GitHub release is not performed here.
Use only with tracks you have rights to, or royalty-free sources.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "config" / "songs_catalog.json"
SONGS_DIR = REPO / "songs"


def load_catalog() -> list[dict]:
    return json.loads(CATALOG.read_text())["songs"]


def release_assets() -> set[str]:
    """List filenames already on songs-bank release (best-effort)."""
    try:
        r = subprocess.run(
            ["gh", "release", "view", "songs-bank", "--json", "assets", "--jq", ".assets[].name"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return {line.strip() for line in r.stdout.splitlines() if line.strip()}
    except Exception:
        pass
    return set()


def main():
    catalog = load_catalog()
    present = release_assets()
    local = {p.name for p in SONGS_DIR.glob("*.mp3")}
    missing = [s for s in catalog if s["file"] not in present and s["file"] not in local]
    print(f"Catalog: {len(catalog)} | On release: {len(present)} | Local: {len(local)} | Missing: {len(missing)}")
    if not missing:
        print("All catalog songs present.")
        return
    print("Missing files (not auto-downloaded — copyrighted commercial tracks):")
    for s in missing[:20]:
        print(f"  - {s['file']}  {s['title']} – {s['artist']}")
    if len(missing) > 20:
        print(f"  ... and {len(missing) - 20} more")
    print("\nTo populate: upload licensed/royalty-free mp3s named exactly as in the catalog")
    print("to the songs-bank release or the local songs/ folder.")


if __name__ == "__main__":
    main()
