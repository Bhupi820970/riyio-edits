"""Pre-fetched source clip pool (draft-style release `clip-pool`, plain JSON manifest `pool.json`).

Why: riyio-v2 used to search + download every source during the run; when RapidAPI or a search had a bad
moment the run had nothing. scripts/clip_pool.py (workflow clip-pool.yml) keeps ~TARGET clean, official,
>=1080p source videos ready; refill starts when usable clips drop to REFILL_AT (50) or below and runs back to
~TARGET (100). run_v2.py tries pool clips first (download from the release, no RapidAPI call) and marks each
one used (or rejected) so a pool clip is never used twice.

Manifest (data only): {"refilling": bool, "updated": iso, "clips": [{"id", "url", "title", "channel", "genre",
"file", "w", "h", "dur", "added", "state": "ready"|"used"|"rejected", "note"}]}
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

RELEASE = "clip-pool"
MANIFEST = "pool.json"
REFILL_AT = int(os.environ.get("POOL_REFILL_AT", "50"))
TARGET = int(os.environ.get("POOL_TARGET", "100"))
MIN_LONG_SIDE = 1920          # >= 1080p (1920x1080 or 1080x1920)
VID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")


def repo() -> str:
    return os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY") or "Bhupi820970/riyio-edits"


def vid_of(url: str) -> str:
    m = VID_RE.search(url or "")
    return m.group(1) if m else ""


def gh(*args, timeout=300) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def empty() -> dict:
    return {"refilling": True, "updated": "", "clips": []}


# ---------------------------------------------------------------- pure logic (tested)
def usable(doc: dict) -> list[dict]:
    return [c for c in doc.get("clips") or [] if c.get("state") == "ready"]


def refill_plan(doc: dict) -> tuple[bool, int]:
    """(refilling, how many to add). Start at <= REFILL_AT usable, stop at >= TARGET."""
    n = len(usable(doc))
    refilling = bool(doc.get("refilling"))
    if n <= REFILL_AT:
        refilling = True
    elif n >= TARGET:
        refilling = False
    return refilling, (max(0, TARGET - n) if refilling else 0)


def by_url(doc: dict, url: str) -> dict | None:
    v = vid_of(url)
    for c in doc.get("clips") or []:
        if c.get("url") == url or (v and c.get("id") == v):
            return c
    return None


def known_ids(doc: dict) -> set[str]:
    return {c.get("id") for c in doc.get("clips") or [] if c.get("id")}


def set_state(doc: dict, url: str, state: str, note: str = "") -> bool:
    c = by_url(doc, url)
    if not c:
        return False
    c["state"], c["note"] = state, note[:160]
    return True


def balanced_order(entries: list[dict], genres: list[str]) -> list[dict]:
    """Round-robin across genres so one genre does not eat the whole pool."""
    buckets = {g: [e for e in entries if e.get("genre") == g] for g in genres}
    out = []
    while any(buckets.values()):
        for g in genres:
            if buckets[g]:
                out.append(buckets[g].pop(0))
    return out + [e for e in entries if e.get("genre") not in genres]


# ---------------------------------------------------------------- release I/O
def load(work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    p = work / MANIFEST
    p.unlink(missing_ok=True)
    r = gh("release", "download", RELEASE, "--repo", repo(), "-p", MANIFEST, "-D", str(work), "--clobber", timeout=120)
    if r.returncode != 0:
        return empty()
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) and isinstance(d.get("clips"), list) else empty()
    except (OSError, ValueError):
        return empty()


def save(doc: dict, work: Path) -> bool:
    doc["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    p = work / MANIFEST
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    ensure_release()
    for _ in range(3):
        if gh("release", "upload", RELEASE, str(p), "--repo", repo(), "--clobber", timeout=120).returncode == 0:
            return True
    return False


def ensure_release() -> None:
    if gh("release", "view", RELEASE, "--repo", repo(), timeout=60).returncode != 0:
        gh("release", "create", RELEASE, "--repo", repo(), "--title", "RIYIO clip pool",
           "--notes", "Pre-fetched official source clips (data for riyio-v2). Never published.", "--draft", timeout=60)


def download(entry: dict, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmpdir = out.parent / "_pool_dl"
    tmpdir.mkdir(exist_ok=True)
    r = gh("release", "download", RELEASE, "--repo", repo(), "-p", entry["file"], "-D", str(tmpdir), "--clobber",
           timeout=900)
    got = tmpdir / entry["file"]
    if r.returncode != 0 or not got.exists() or got.stat().st_size < 500_000:
        return False
    got.replace(out)
    return True
