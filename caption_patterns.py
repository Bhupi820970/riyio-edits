"""Pro-style punchy neon captions (cyan/pink/yellow/purple) — big, bold, dialogue-synced.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent
HISTORY_PATH = REPO / "history.json"
FONTS_DIR = REPO / "fonts"

# Pro neon palette matching Vice Cartel style
CYAN = (0, 255, 255)
PINK = (255, 0, 180)
YELLOW = (255, 255, 0)
PURPLE = (180, 0, 255)
WHITE = (255, 255, 255)
ORANGE = (255, 140, 0)

FONT_MAP = {
    "Montserrat Medium": "Montserrat-Medium.ttf",
    "Roboto Condensed": "RobotoCondensed-Regular.ttf",
    "Cinzel": "Cinzel-Regular.ttf",
}

_P = [
    ("P01", "Neon punch", [0.0], 0.85, 0.0, 3, (.11, .09, .06), [CYAN, PINK, YELLOW, WHITE], .28, "Montserrat Medium", "pop"),
    ("P02", "Cyan yellow", [-0.4], 0.88, 0.0, 2, (.105, .085, .055), [CYAN, YELLOW, WHITE], .25, "Roboto Condensed", "slide"),
    ("P03", "Pink purple", [0.0], 0.82, 0.0, 3, (.10, .08, .05), [PINK, PURPLE, WHITE], .32, "Montserrat Medium", "fade"),
    ("P04", "Yellow cyan", [0.3], 0.9, 0.0, 2, (.115, .09, .06), [YELLOW, CYAN, WHITE], .22, "Roboto Condensed", "pop"),
]

PATTERNS = [{
    "id": i, "name": n, "y": y, "gap": g, "nudge": nu, "words": w,
    "key": k[0], "key_long": k[1], "filler": k[2], "keys": pal,
    "no_face_y": nf, "font_hint": fh, "anim": anim, "classic": i == "P01",
} for i, n, y, g, nu, w, k, pal, nf, fh, anim in _P]

ROTATION = [p["id"] for p in PATTERNS]
BY_ID = {p["id"]: p for p in PATTERNS}
BY_ID["P00"] = BY_ID["original"] = BY_ID["P01"]


def load_history() -> dict:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except Exception:
            pass
    return {"used_patterns": [], "uploaded": [], "source_ids": [], "songs": []}


def save_history(h: dict) -> None:
    HISTORY_PATH.write_text(json.dumps(h, indent=2))


def pick_pattern() -> dict:
    h = load_history()
    used = set(h.get("used_patterns", [])[-10:])
    candidates = [p for p in PATTERNS if p["id"] not in used] or PATTERNS
    chosen = candidates[0]
    h.setdefault("used_patterns", []).append(chosen["id"])
    save_history(h)
    return chosen


def get(pid: str | None) -> dict:
    return BY_ID.get(pid or "P01", PATTERNS[0])


def font_path(hint: str | None = None) -> str:
    name = FONT_MAP.get(hint or "Montserrat Medium", "Montserrat-Medium.ttf")
    p = FONTS_DIR / name
    if p.exists():
        return str(p)
    for f in FONTS_DIR.glob("*.ttf"):
        return str(f)
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
