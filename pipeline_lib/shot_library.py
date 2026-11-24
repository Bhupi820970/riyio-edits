"""Shot library per title (idea 5): config/shot_library.json, committed back by the workflow.

{ "<title key>": {"title": "...", "sources": {"<youtube id>": {"url", "title", "channel", "updated",
                                                            "shots": [{"s", "e", "energy", "kind", "loud",
                                                                       "motion", "hash"}]}}}}
Later videos of the same title download a known-good source straight from the library (already logo-screened and
shot-picked: no search call, no channel listing, no Gemini shot pass), so they need fewer RapidAPI calls.
No-repeat rules still run per video in montage_select.select/audit. Pure functions except load/save.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

PATH = Path("config/shot_library.json")
MAX_SHOTS = 40          # per source
MAX_SOURCES = 8         # per title
MAX_TITLES = 400
GOOD_SCORE = 6.0        # Chunk.score() needed to be saved as a "good" montage shot


def key(title: str) -> str:
    t = re.sub(r"\(\s*(19|20)\d\d\s*\)", "", (title or "").lower())
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def load(path: Path = PATH) -> dict:
    try:
        d = json.loads(Path(path).read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(lib: dict, path: Path = PATH) -> None:
    if len(lib) > MAX_TITLES:   # keep the most recently updated titles
        keep = sorted(lib, key=lambda k: -max((s.get("updated") or 0) for s in lib[k]["sources"].values()))
        lib = {k: lib[k] for k in keep[:MAX_TITLES]}
    Path(path).write_text(json.dumps(lib, indent=1, sort_keys=True) + "\n")


def shot_record(c) -> dict:
    """Chunk (montage_select.Chunk) -> stored shot."""
    return {"s": round(float(c.s), 2), "e": round(float(c.e), 2), "energy": round(float(c.energy), 1),
            "kind": c.kind or "", "loud": round(float(getattr(c, "loud", 0.0)), 1),
            "motion": round(float(c.motion), 1), "hash": str(int(c.hash))}


def add(lib: dict, title: str, vid: str, meta: dict, chunks: list, min_score: float = GOOD_SCORE,
        now: float | None = None) -> int:
    """Save the good montage shots of one source under its title. Returns how many shots are stored."""
    k = key(title)
    if not k or not vid:
        return 0
    good = sorted((c for c in chunks if c.score() >= min_score), key=lambda c: -c.score())[:MAX_SHOTS]
    if not good:
        return 0
    entry = lib.setdefault(k, {"title": title, "sources": {}})
    src = entry["sources"].setdefault(vid, {})
    old = {(round(x["s"], 1)): x for x in src.get("shots") or []}
    for c in good:
        old[round(float(c.s), 1)] = shot_record(c)
    shots = sorted(old.values(), key=lambda x: -(2 * x.get("energy", 0) + x.get("motion", 0) / 8
                                                  + 0.4 * x.get("loud", 0)))[:MAX_SHOTS]
    src.update({"url": meta.get("url", ""), "title": meta.get("title", ""), "channel": meta.get("channel", ""),
                "updated": int(now if now is not None else time.time()),
                "shots": sorted(shots, key=lambda x: x["s"])})
    if len(entry["sources"]) > MAX_SOURCES:
        drop = sorted(entry["sources"], key=lambda v: entry["sources"][v].get("updated") or 0)
        for v in drop[: len(entry["sources"]) - MAX_SOURCES]:
            entry["sources"].pop(v, None)
    return len(src["shots"])


def sources_for(lib: dict, title: str, exclude_ids: set | None = None, exclude_urls: set | None = None) -> list[dict]:
    """Known-good sources of this title, richest first: [{id, url, title, channel, shots}]."""
    entry = lib.get(key(title)) or {}
    out = []
    for vid, s in (entry.get("sources") or {}).items():
        if exclude_ids and vid in exclude_ids:
            continue
        if exclude_urls and s.get("url") in exclude_urls:
            continue
        if not s.get("url") or not s.get("shots"):
            continue
        out.append({"id": vid, **s})
    return sorted(out, key=lambda s: -sum(x.get("energy", 0) for x in s["shots"]))


def as_gemini_shots(shots: list[dict]) -> list[dict]:
    """Stored shots -> montage_select.apply_gemini input (t = middle of the shot)."""
    return [{"t": round((x["s"] + x["e"]) / 2, 2), "energy": max(4.0, float(x.get("energy") or 0) or 5.0),
             "kind": x.get("kind") or "library", "reason": "shot library (earlier video)"} for x in shots]
