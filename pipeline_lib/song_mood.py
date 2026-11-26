"""Song by mood (idea 3): pick the songs-bank track by the scene's mood + tempo.

Gemini Pass 1 tags the scene with scene_mood (comedy | dark | epic | emotional | hype). Every library song has a
mood (config/songs_catalog.json) plus a cached BPM / loudness tag (config/song_tags.json, written once by
scripts/tag_songs.py and topped up by every run). rank_songs() only returns songs whose mood is allowed for the
scene (an emotional or romance song never goes on a comedy / hype / dark scene), tempo-matched first.
Pure functions except load/save.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SCENE_MOODS = ("comedy", "dark", "epic", "emotional", "hype")
# allowed song moods per scene mood, best first
ALLOWED = {
    "comedy": ["hype", "aggressive", "epic"],      # epic only as the last resort (never emotional/romance)
    "dark": ["dark", "aggressive", "epic"],
    "epic": ["epic", "aggressive", "dark", "hype"],
    "emotional": ["emotional", "romance", "epic"],
    "hype": ["hype", "aggressive", "epic"],
}
# preferred BPM range per scene mood (tempo folded into 70-180 first)
BPM_RANGE = {
    "comedy": (105, 150),
    "dark": (80, 135),
    "epic": (70, 140),
    "emotional": (60, 110),
    "hype": (115, 175),
}
# old director mood names -> scene mood (fallback when Gemini gives no scene_mood)
LEGACY = {"dark_hype": "dark", "epic_cinematic": "epic", "emotional_romance": "emotional", "cold_sigma": "dark"}

CATALOG = Path("config/songs_catalog.json")
TAGS = Path("config/song_tags.json")


def scene_mood(plan: dict) -> str:
    """Normalised scene mood from the director plan (scene_mood first, then the legacy mood, else dark)."""
    for key in ("scene_mood", "mood"):
        v = str(plan.get(key) or "").strip().lower().replace("-", "_").replace(" ", "_")
        if v in SCENE_MOODS:
            return v
        if v in LEGACY:
            return LEGACY[v]
        for m in SCENE_MOODS:
            if v.startswith(m):
                return m
        if v in ("funny", "humor", "humour", "comedic", "light"):
            return "comedy"
        if v in ("sad", "romance", "romantic", "tragic"):
            return "emotional"
    return "dark"


def fold_bpm(bpm: float) -> float:
    """librosa often reports half / double time: fold into 70-180."""
    b = float(bpm or 0)
    if b <= 0:
        return 0.0
    while b < 70:
        b *= 2
    while b > 180:
        b /= 2
    return round(b, 1)


def tempo_fit(bpm: float, mood: str) -> float:
    """0 = inside the preferred range, else distance in BPM (unknown tempo = 15, i.e. after good fits)."""
    b = fold_bpm(bpm)
    if not b:
        return 15.0
    lo, hi = BPM_RANGE.get(mood, (70, 180))
    return 0.0 if lo <= b <= hi else float(min(abs(b - lo), abs(b - hi)))


def allowed(scene: str, song_mood: str) -> bool:
    return song_mood in ALLOWED.get(scene, ALLOWED["dark"])


def rank_songs(scene: str, songs: list[dict], tags: dict, rng: random.Random | None = None) -> list[str]:
    """Files allowed for this scene mood: by mood preference, then tempo fit, shuffled inside ties."""
    rng = rng or random.Random()
    prefs = ALLOWED.get(scene, ALLOWED["dark"])
    cands = []
    for s in songs:
        f, m = s.get("file") or "", s.get("mood") or ""
        if not f or m not in prefs:
            continue
        t = tags.get(f) or {}
        fit = tempo_fit(t.get("bpm") or 0, scene)
        if t.get("bpm") and fit > 30:          # far off-tempo (e.g. a 60 BPM ballad on a hype scene): skip
            continue
        cands.append((prefs.index(m), min(fit, 20.0) // 10, rng.random(), f))
    return [f for *_, f in sorted(cands)]


def only_available(songs: list[dict], bank: set[str] | None) -> list[dict]:
    """Catalog entries whose mp3 is really in the songs-bank release (bank=None: listing failed, keep all)."""
    if not bank:
        return list(songs)
    return [s for s in songs if (s.get("file") or "") in bank]


def load_catalog(path: Path = CATALOG) -> list[dict]:
    try:
        return json.loads(Path(path).read_text()).get("songs") or []
    except Exception:
        return []


def load_tags(path: Path = TAGS) -> dict:
    try:
        d = json.loads(Path(path).read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_tags(tags: dict, path: Path = TAGS) -> None:
    Path(path).write_text(json.dumps(dict(sorted(tags.items())), indent=1) + "\n")


def tag_entry(mood: str, tempo: float, rms: float | None = None, drop: float | None = None) -> dict:
    e = {"mood": mood, "bpm": fold_bpm(tempo)}
    if rms is not None:
        e["rms"] = round(float(rms), 4)
    if drop is not None:
        e["drop_s"] = round(float(drop), 2)
    return e
