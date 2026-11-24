"""Speaker-side caption styles for riyio's Remotion JuraijEdit.

Copied/adapted (read-only) from Bhupi820970/pro-edit:
  - caption_patterns.py : the 15 beside-speaker patterns P01-P15 (riyio already carries the same file)
  - vicestyle.py        : FILLER, clean_word, chunk rules, style_items, render_block line layout,
                          find_faces (OpenCV YuNet), person_boxes, _inter, place_beside, read_frames
Plus "R00" = the RIYIO reference glow look (Playfair serif, coloured glow) on the same placement engine.
Layout is measured here with PIL using the exact font files Remotion loads (remotion/public/fonts),
then Remotion draws text at the computed boxes with word-level reveal (lip sync).
"""
from __future__ import annotations
import os, re, zlib
from pathlib import Path

import caption_patterns as CP

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "remotion" / "public" / "fonts"
FONTS = {"anton": FONT_DIR / "Anton-Regular.ttf", "playfair": FONT_DIR / "PlayfairDisplay.ttf"}
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")

FILLER = set("""a an the to of and or but so is are am was were be been i you he she it we they
me him her us them my your his its our their this that these those in on at for with as by
from up out do does did not no yes yeah oh uh um huh hey just got get gonna gotta will would
can could should there here what who how why when where if then than all some kind""".split())

RED, ORANGE, PINK, GREEN, BLUE, YELLOW = (244, 63, 94), (251, 146, 60), (244, 114, 182), (52, 211, 153), (56, 189, 248), (250, 204, 21)
R00 = {"id": "R00", "name": "RIYIO reference glow (serif)", "y": [0.0], "gap": 0.9, "nudge": 0.0, "words": 4,
       "key": .060, "key_long": .052, "filler": .044, "keys": [RED, ORANGE, PINK, GREEN, BLUE, YELLOW],
       "no_face_y": .55, "classic": False, "font": "playfair", "look": "glow", "place": "center"}

STYLES = {"R00": R00}
for _p in CP.PATTERNS:
    STYLES[_p["id"]] = {**_p, "font": "anton", "look": "shadow"}

# fitting styles per Gemini mood; the run rotates inside the list (all 16 styles are used)
BY_MOOD = {
    "dark_hype": ["R00", "P10", "P08", "P14"],
    "cold_sigma": ["P01", "R00", "P09", "P06"],
    "epic_cinematic": ["P04", "P12", "P07", "R00", "P11"],
    "emotional_romance": ["P03", "P15", "P13", "R00"],
    "hype": ["P05", "P02", "P11", "P06"],
}


REF_LOOK_DEFAULT = True   # BiBi Nov 24: captions like ref1/ref2 (serif, coloured glow, centred on the speaker)


def pick_style(mood: str, seed: str = "") -> dict:
    forced = os.environ.get("CAPTION_STYLE", "").strip().upper()
    if forced in STYLES:
        return STYLES[forced]
    if REF_LOOK_DEFAULT:
        return R00
    pool = BY_MOOD.get(mood or "", BY_MOOD["dark_hype"])
    n = int(os.environ.get("GITHUB_RUN_NUMBER") or 0) + zlib.crc32(seed.encode())
    return STYLES[pool[n % len(pool)]]


def clean_word(w: str) -> str:
    return re.sub(r"[^A-Za-z0-9'?!.,]", "", w).upper().rstrip(".,")


_FONT_CACHE: dict = {}


def _font(name: str, size: int):
    from PIL import ImageFont
    key = (name, size)
    if key not in _FONT_CACHE:
        f = ImageFont.truetype(str(FONTS[name]), size)
        if name == "playfair":
            try:
                f.set_variation_by_axes([800])
            except Exception:
                pass
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


# Caption text sizes on the 1080x1350 frame, matched to the reference edits (ref1/ref2: caption cap height
# ~5-6% of the frame, ~45-70 px keys on 1080 wide). Never bigger than this, never unreadably small.
SIZE_LIMITS = {"filler": (34, 60), "key": (52, 96), "punch": (64, 112)}
BASE_FRAC = 0.62      # size_h = W * BASE_FRAC -> pro-edit key .098 ~ 66 px
WORDS_SCALE = {1: 1.22, 2: 1.1, 3: 1.0}   # fewer words -> bigger, 4 words -> 0.92


def clamp_size(px: float, kind: str) -> int:
    lo, hi = SIZE_LIMITS[kind]
    return int(min(max(px, lo), hi))


def free_width(main, pat, W: int) -> float:
    """Width available beside the speaker's face (pro-edit puts the caption next to the speaker)."""
    margin = W * 0.05
    if not main:
        return W * 0.62
    fx = (main[0] + main[2]) / 2 * W
    fw = (main[2] - main[0]) * W
    right = W - margin - (fx + fw * pat["gap"])
    left = fx - fw * pat["gap"] - margin
    return max(W * 0.38, min(W * 0.62, max(left, right)))


def style_items(ch: list[dict], pat: dict, size_h: float, color_i: int, punch_i: int | None):
    """pro-edit style_items: filler words small + white, key words big + next palette colour."""
    items = []
    for w in ch:
        t = clean_word(w["word"])
        base = re.sub(r"[^a-z']", "", t.lower())
        is_punch = punch_i is not None and w.get("i") == punch_i
        if not t:
            continue
        if (base in FILLER or len(base) <= 2) and not is_punch:
            items.append({"t": t, "c": "#FFFFFF", "size": clamp_size(size_h * pat["filler"], "filler"), "small": True,
                          "s": w["s"], "e": w["e"]})
        else:
            col = (255, 46, 60) if is_punch else tuple(pat["keys"][color_i % len(pat["keys"])])
            color_i += 1
            size = clamp_size(size_h * (pat["key"] if len(base) <= 8 else pat["key_long"]) * (1.25 if is_punch else 1.0),
                              "punch" if is_punch else "key")
            items.append({"t": t, "c": "#%02X%02X%02X" % col, "size": size, "small": False, "s": w["s"], "e": w["e"],
                          "punch": is_punch})
    return items, color_i


def layout_block(items: list[dict], font: str, look: str):
    """pro-edit render_block geometry: consecutive small words share a line, big words get their own."""
    lines, cur, cur_small = [], [], None
    for it in items:
        if cur and (not it["small"] or not cur_small):
            lines.append(cur)
            cur = []
        cur.append(it)
        cur_small = it["small"]
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        widths, lh = [], 0
        for it in ln:
            bb = _font(font, it["size"]).getbbox(it["t"])
            widths.append(bb[2] - bb[0])
            lh = max(lh, bb[3])
        sp = int(max(it["size"] for it in ln) * 0.25)
        out.append({"words": ln, "w": sum(widths) + sp * (len(ln) - 1), "h": lh, "sp": sp})
    pad = 40 if look == "glow" else 24
    bw = max(l["w"] for l in out) + pad * 2
    bh = sum(l["h"] for l in out) + 6 * (len(out) - 1) + pad * 2
    return out, bw, bh, pad


# ---------- faces (pro-edit find_faces / person_boxes / _inter) ----------
_FACE = None


def _detector():
    global _FACE
    if _FACE is None:
        import cv2
        mp = ROOT / "models" / "face_detection_yunet_2023mar.onnx"
        if not mp.exists():
            mp.parent.mkdir(exist_ok=True)
            import urllib.request
            urllib.request.urlretrieve(YUNET_URL, mp)
        _FACE = cv2.FaceDetectorYN.create(str(mp), "", (640, 360), 0.55)
    return _FACE


def find_faces(frame_bgr) -> list[tuple]:
    import cv2
    det = _detector()
    h, w = frame_bgr.shape[:2]
    sc = 640 / w
    small = cv2.resize(frame_bgr, (640, int(h * sc)))
    det.setInputSize((small.shape[1], small.shape[0]))
    _, faces = det.detect(small)
    if faces is None:
        return []
    sw, sh = small.shape[1], small.shape[0]
    return [(float(f[0] / sw), float(f[1] / sh), float((f[0] + f[2]) / sw), float((f[1] + f[3]) / sh)) for f in faces]


def read_frames(video: Path, idxs: set[int]) -> dict:
    import cv2
    out, cap = {}, cv2.VideoCapture(str(video))
    last = max(idxs) if idxs else -1
    fi = 0
    while fi <= last:
        if not cap.grab():
            break
        if fi in idxs:
            ok, fr = cap.retrieve()
            if ok:
                out[fi] = fr
        fi += 1
    cap.release()
    return out


def _inter(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return float(w * h) if w > 0 and h > 0 else 0.0


def person_boxes(faces, W, H):
    out = []
    for x0, y0, x1, y1 in faces:
        X0, Y0, X1, Y1 = x0 * W, y0 * H, x1 * W, y1 * H
        fw, fh = X1 - X0, Y1 - Y0
        out.append((X0 - 0.25 * fw, Y0 - 0.25 * fh, X1 + 0.25 * fw, Y1 + 0.25 * fh))
    return out


def place_beside(bw, bh, pat, step, faces, main, W, H, band, alt):
    """pro-edit place_beside: beside the speaker, away from the face, mirrored/shifted so no face is covered.
    band = (top, bottom) of the movie picture, captions stay inside it."""
    margin = int(W * 0.05)
    top, bot = band
    dy = pat["y"][step % len(pat["y"])]
    cands = []
    if main:
        fx = (main[0] + main[2]) / 2 * W
        fw = (main[2] - main[0]) * W
        fh = (main[3] - main[1]) * H
        fy = (main[1] + main[3]) / 2 * H
        side = "right" if fx < W / 2 else "left"
        for sd in (side, "left" if side == "right" else "right"):
            for ddy in (dy, dy - 0.7, dy + 0.7, 0.0):
                x = int(min(fx + fw * pat["gap"], W - margin - bw)) if sd == "right" else int(max(fx - fw * pat["gap"] - bw, margin))
                cx = x + bw / 2
                x += int(pat["nudge"] * W * (1 if cx < W / 2 else -1))
                y = int(fy + ddy * fh - bh * 0.5)
                cands.append((x, y, "left" if sd == "right" else "right", "beside" if sd == side else "beside-mirror"))
    else:
        sd = "left" if alt % 2 == 0 else "right"
        for s2 in (sd, "right" if sd == "left" else "left"):
            x = margin if s2 == "left" else W - margin - bw
            y = int(top + (bot - top) * pat["no_face_y"] - bh / 2)
            cands.append((x, y, "left" if s2 == "left" else "right", f"noface-{s2}"))
    best = None
    for x, y, align, zone in cands:
        y = max(top, min(y, bot - bh))
        x = max(margin // 2, min(x, W - bw - margin // 2))
        box = (x + 12, y + 12, x + bw - 12, y + bh - 12)
        ov = int(sum(_inter(box, pb) for pb in person_boxes(faces, W, H)))
        if best is None or ov < best[3]:
            best = (x, y, align, ov, zone)
        if ov == 0:
            break
    return best


def place_center(bw, bh, pat, faces, main, W, H, band):
    """ref1/ref2 placement: horizontally centred on the speaker, at chin / upper-chest height (just under the
    face), or mid-picture when no face is found. Moves above the face / to picture centre if it would cover one."""
    margin = int(W * 0.05)
    top, bot = band
    cands = []
    if main:
        fx = (main[0] + main[2]) / 2 * W
        fh = (main[3] - main[1]) * H
        cx = min(max(fx, margin + bw / 2), W - margin - bw / 2)
        cands.append((int(cx - bw / 2), int(main[3] * H + 0.15 * fh), "center-chin"))
        cands.append((int(W / 2 - bw / 2), int(top + (bot - top) * pat["no_face_y"] - bh / 2), "center-mid"))
        cands.append((int(cx - bw / 2), int(main[1] * H - 0.1 * fh - bh), "center-above"))
    else:
        cands.append((int(W / 2 - bw / 2), int(top + (bot - top) * pat["no_face_y"] - bh / 2), "center-noface"))
    best = None
    for x, y, zone in cands:
        y = max(top, min(y, bot - bh))
        x = max(margin // 2, min(x, W - bw - margin // 2))
        box = (x + 12, y + 12, x + bw - 12, y + bh - 12)
        ov = int(sum(_inter(box, (f[0] * W, f[1] * H, f[2] * W, f[3] * H)) for f in faces))
        if best is None or ov < best[3]:
            best = (x, y, "center", ov, zone)
        if ov == 0:
            break
    return best


def build_events(groups: list[dict], punch_i: int | None, pat: dict, dialogue_video: Path,
                 W: int, H: int, band: tuple, fps: int) -> tuple[list[dict], dict]:
    """groups: [{'start','end','words':[{word,s,e,i}]}] -> Remotion caption events with x/y/lines."""
    size_h = W * BASE_FRAC  # sized to the frame width like the reference edits (old: ~H -> 150 px, too big)
    need = set()
    for g in groups:
        f0, f1 = int(round(g["start"] * fps)), int(round(g["end"] * fps))
        need |= {f0, (f0 + f1) // 2, max(f0, f1 - 1)}
    faces_at, face_ok = {}, True
    try:
        frames = read_frames(dialogue_video, need)
        faces_at = {fi: find_faces(fr) for fi, fr in frames.items()}
    except Exception as e:
        face_ok = False
        print("FACE detection unavailable, using no-face placement:", repr(e)[:200], flush=True)
    events, color_i, alt, zones = [], 0, 0, {}
    for n, g in enumerate(groups):
        f0, f1 = int(round(g["start"] * fps)), int(round(g["end"] * fps))
        fset = []
        for fi in (f0, (f0 + f1) // 2, max(f0, f1 - 1)):
            fset += faces_at.get(fi, [])
        mid = faces_at.get((f0 + f1) // 2, []) or faces_at.get(f0, [])
        main = max(mid, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if mid else None
        nwords = len([w for w in g["words"] if clean_word(w["word"])])
        ci0, k = color_i, WORDS_SCALE.get(nwords, 0.92)
        avail = W * 0.8 if pat.get("place") == "center" else free_width(main, pat, W)
        while True:  # pro-edit proportions; shrink (down to the readable minimum) until it fits beside the speaker
            items, color_i = style_items(g["words"], pat, size_h * k, ci0, punch_i)
            if not items:
                break
            lines, bw, bh, pad = layout_block(items, pat["font"], pat["look"])
            if (bh <= 0.6 * (band[1] - band[0]) and bw <= avail) or k < 0.7:
                break
            k *= 0.93
        if not items:
            continue
        if pat.get("place") == "center":
            x, y, align, ov, zone = place_center(bw, bh, pat, fset, main, W, H, band)
        else:
            x, y, align, ov, zone = place_beside(bw, bh, pat, n, fset, main, W, H, band, alt)
        if not main:
            alt += 1
        zones[zone.split("-")[0]] = zones.get(zone.split("-")[0], 0) + 1
        events.append({"start": g["start"], "end": g["end"], "x": x, "y": y, "w": bw, "h": bh, "pad": pad,
                       "align": align, "zone": zone, "overlap": ov,
                       "punch": any(it.get("punch") for it in items),
                       "lines": [{"h": l["h"], "sp": l["sp"],
                                  "words": [{"t": it["t"], "c": it["c"], "size": it["size"], "s": round(it["s"], 3)}
                                            for it in l["words"]]} for l in lines]})
    return events, {"faces": face_ok, "zones": zones}


def watermark_size(text: str, W: int, frac: float = 0.07) -> int:
    """Anton font size whose text width is ~7% of the frame width (VICE CARTEL mark look)."""
    size = 10
    for s in range(10, 120):
        bb = _font("anton", s).getbbox(text)
        if bb[2] - bb[0] > W * frac:
            break
        size = s
    return size
