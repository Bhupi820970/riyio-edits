"""Pro-style punchy neon captions matching Vice Cartel / proedit approved look.

Words beside the speaker, key words big + colored, fillers small white, hard shadow,
exact approved hot pink, dialogue-synced, multi-word chunks.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent
HISTORY_PATH = REPO / "history.json"
FONTS_DIR = REPO / "fonts"

# Exact proedit / Vice Cartel neon palette
PINK = (255, 46, 196)          # approved hot pink from vice_style_code
CYAN = (0, 238, 255)
YELLOW = (255, 228, 40)
PURPLE = (178, 92, 255)
ORANGE = (255, 140, 0)
LIME = (170, 255, 0)
GOLD = (255, 200, 40)
WHITE = (255, 255, 255)

FONT_MAP = {
    "Montserrat Medium": "Montserrat-Medium.ttf",
    "Roboto Condensed": "RobotoCondensed-Regular.ttf",
    "Cinzel": "Cinzel-Regular.ttf",
}

_P = [
    ("P01", "Original beside-mid (approved)", [0.0], 0.9, 0.0, 3, (.098, .082, .052), [CYAN, PINK, YELLOW, PURPLE], .30, "Montserrat Medium", "pop"),
    ("P02", "Beside-upper", [-0.65], 0.9, 0.0, 3, (.098, .082, .052), [PINK, CYAN, YELLOW, ORANGE], .22, "Montserrat Medium", "pop"),
    ("P03", "Beside-lower", [0.75], 0.9, 0.0, 3, (.096, .080, .050), [YELLOW, PINK, CYAN, LIME], .45, "Roboto Condensed", "slide"),
    ("P04", "Stepping down", [-0.6, 0.0, 0.6], 0.9, 0.0, 3, (.098, .082, .052), [CYAN, PINK, PURPLE, GOLD], .30, "Montserrat Medium", "pop"),
    ("P05", "2-word punch", [0.0], 0.9, 0.0, 2, (.108, .090, .052), [PINK, YELLOW, CYAN, ORANGE], .30, "Roboto Condensed", "pop"),
    ("P06", "Big keys tiny fillers", [0.0], 0.9, 0.0, 3, (.116, .096, .042), [PINK, CYAN, YELLOW, PURPLE], .30, "Montserrat Medium", "fade"),
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
    used = set(h.get("used_patterns", [])[-8:])
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
