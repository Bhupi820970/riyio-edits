"""20 sleek, compact beside-speaker caption patterns (P01–P20).

Captions stay COMPACT (max ~12–15% of frame width), never fat/blocky,
never covering faces, never bottom-edge subtitles. Always float BESIDE
the speaker with soft outer glow + clean drop shadow.

Fonts loaded from fonts/ (Cinzel, Cormorant Garamond, Playfair Display Italic,
Montserrat Light/Medium, Roboto Condensed). Multi-color keyword highlights.
Tracks used pattern IDs in history.json (no repeat for ~21 videos / 3 days).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent
HISTORY_PATH = REPO / "history.json"
FONTS_DIR = REPO / "fonts"

# Refined multi-color palettes
CHAMPAGNE_GOLD = (212, 175, 55)
IVORY = (255, 245, 230)
ICY_CYAN = (170, 230, 255)
SOFT_ROSE = (255, 182, 193)
SILVER = (192, 192, 192)
LAVENDER = (230, 230, 250)
PEARL = (240, 234, 214)
AMBER = (255, 191, 0)
CREAM = (255, 253, 208)
MINT = (189, 252, 201)
CRIMSON = (220, 20, 60)
SUNSET_PEACH = (255, 204, 153)
WHITE = (255, 255, 255)

FONT_MAP = {
    "Cinzel": "Cinzel-Regular.ttf",
    "Cormorant Garamond": "CormorantGaramond-Regular.ttf",
    "Playfair Display Italic": "PlayfairDisplay-Italic.ttf",
    "Montserrat Light": "Montserrat-Light.ttf",
    "Montserrat Medium": "Montserrat-Medium.ttf",
    "Roboto Condensed": "RobotoCondensed-Regular.ttf",
}

_P = [
    ("P01", "Neon beside-mid", [0.0], 0.9, 0.0, 3, (.095, .078, .048), [ICY_CYAN, CRIMSON, AMBER, WHITE], .30, "Montserrat Medium", "pop"),
    ("P02", "Icy upper-left", [-0.55], 0.9, 0.0, 3, (.070, .060, .046), [ICY_CYAN, WHITE, SILVER], .22, "Montserrat Light", "slide"),
    ("P03", "Soft rose mid-right", [0.0], 0.88, 0.02, 3, (.068, .058, .044), [SOFT_ROSE, SILVER, WHITE], .30, "Cormorant Garamond", "fade"),
    ("P04", "Lavender stepped diagonal", [-0.5, 0.0, 0.5], 0.82, 0.0, 3, (.070, .060, .046), [LAVENDER, PEARL, WHITE], .26, "Playfair Display Italic", "drop"),
    ("P05", "Amber cream upper", [-0.45], 0.92, 0.0, 2, (.074, .064, .048), [AMBER, CREAM, IVORY], .20, "Cinzel", "reveal"),
    ("P06", "Mint white close", [0.0], 0.75, 0.03, 3, (.066, .056, .042), [MINT, WHITE, SILVER], .32, "Montserrat Medium", "pop"),
    ("P07", "Crimson glow far", [-0.15], 1.05, 0.0, 3, (.070, .060, .046), [CRIMSON, WHITE, IVORY], .28, "Cormorant Garamond", "slide"),
    ("P08", "Sunset peach punch", [0.0], 0.88, 0.0, 2, (.076, .066, .048), [SUNSET_PEACH, IVORY, WHITE], .30, "Playfair Display Italic", "fade"),
    ("P09", "Pearl split-side", [-0.35, 0.35], 0.85, 0.0, 3, (.068, .058, .044), [PEARL, LAVENDER, WHITE], .26, "Cinzel", "drop"),
    ("P10", "Gold ivory compact", [0.0], 0.8, 0.0, 3, (.064, .054, .040), [CHAMPAGNE_GOLD, IVORY, CREAM], .34, "Montserrat Light", "reveal"),
    ("P11", "Cyan silver step", [0.4, 0.0, -0.4], 0.9, 0.0, 3, (.070, .060, .046), [ICY_CYAN, SILVER, WHITE], .28, "Cormorant Garamond", "pop"),
    ("P12", "Rose gold upper-right", [-0.5], 0.95, 0.0, 2, (.072, .062, .048), [SOFT_ROSE, CHAMPAGNE_GOLD, WHITE], .22, "Playfair Display Italic", "slide"),
    ("P13", "Lavender wave", [-0.4, 0.0, 0.4, 0.0], 0.85, 0.0, 3, (.068, .058, .044), [LAVENDER, PEARL, SILVER], .30, "Cinzel", "fade"),
    ("P14", "Amber mint mix", [0.0], 0.82, 0.02, 3, (.066, .056, .042), [AMBER, MINT, IVORY], .32, "Montserrat Medium", "drop"),
    ("P15", "Crimson cream lower", [0.45], 1.0, 0.0, 2, (.070, .060, .046), [CRIMSON, CREAM, WHITE], .40, "Cormorant Garamond", "reveal"),
    ("P16", "Peach silver diagonal", [-0.3, 0.2], 0.88, 0.0, 3, (.068, .058, .044), [SUNSET_PEACH, SILVER, IVORY], .26, "Playfair Display Italic", "pop"),
    ("P17", "Ivory cyan compact", [0.0], 0.78, 0.0, 3, (.064, .054, .040), [IVORY, ICY_CYAN, WHITE], .34, "Cinzel", "slide"),
    ("P18", "Gold rose upper", [-0.48], 0.9, 0.0, 2, (.072, .062, .048), [CHAMPAGNE_GOLD, SOFT_ROSE, PEARL], .22, "Montserrat Light", "fade"),
    ("P19", "Mint lavender step-down", [-0.55, 0.0, 0.55], 0.85, 0.0, 3, (.070, .060, .046), [MINT, LAVENDER, WHITE], .28, "Cormorant Garamond", "drop"),
    ("P20", "Silver pearl far", [-0.1], 1.1, 0.0, 3, (.068, .058, .044), [SILVER, PEARL, IVORY], .30, "Playfair Display Italic", "reveal"),
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
    """Pick a pattern not used in the last ~21 videos."""
    h = load_history()
    used = set(h.get("used_patterns", [])[-21:])
    candidates = [p for p in PATTERNS if p["id"] not in used] or PATTERNS
    chosen = candidates[0]
    h.setdefault("used_patterns", []).append(chosen["id"])
    save_history(h)
    return chosen


def get(pid: str | None) -> dict:
    return BY_ID.get(pid or "P01", PATTERNS[0])


def font_path(hint: str | None = None) -> str:
    name = FONT_MAP.get(hint or "Cinzel", "Cinzel-Regular.ttf")
    p = FONTS_DIR / name
    if p.exists():
        return str(p)
    # fallback to any ttf in fonts/
    for f in FONTS_DIR.glob("*.ttf"):
        return str(f)
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
