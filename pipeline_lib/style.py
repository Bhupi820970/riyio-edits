"""RIYIO reference style helpers (see docs/REFERENCE_STYLE.md). Pure functions, no rendering."""
from __future__ import annotations
import re

W, H = 1080, 1350
FPS = 30
ACCENTS = ["#F43F5E", "#FB923C", "#F472B6", "#34D399", "#38BDF8", "#FACC15"]  # red, orange, pink, green, blue, yellow
FILLERS = {"okay", "ok", "uh", "um", "hmm", "well", "yeah", "oh", "ah", "so", "right"}
IMPACT = {"what", "money", "never", "kill", "dead", "death", "winter", "blood", "war", "king", "power", "die",
          "nothing", "everything", "enough", "now", "mine", "lie", "liar", "secret", "secrets", "danger", "name"}
BANNED_HOOKS = {"she read him cold", "money really talks", "built different", "full throttle", "legacy of blood",
                "winter is finally here", "i am the danger"}

# 16:9 (or any) source -> 4:5 frame, no crop of the main picture; blurred + darkened copy fills top/bottom.
# Grade per spec: contrast ~1.25, saturation ~0.6, brightness ~0.9, teal shadows, crushed blacks, grain, unsharp 5:5:1.0.
GRADE = ("eq=contrast=1.25:saturation=0.62:brightness=-0.035:gamma=0.95,"
         "colorbalance=rs=-0.05:gs=0.0:bs=0.08:rh=0.02:bh=-0.02,"
         "curves=master='0/0 0.08/0.02 0.5/0.48 1/1',"
         "unsharp=5:5:1.0:5:5:0.0,noise=alls=4:allf=t")


def frame_filter(rgb_split: bool = False) -> str:
    fc = (f"[0:v]split=2[a][b];"
          f"[a]scale=270:338:force_original_aspect_ratio=increase,crop=270:338,boxblur=12:2,"
          f"eq=brightness=-0.22:saturation=0.7,scale={W}:{H}[bg];"
          f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{GRADE}")
    if rgb_split:
        fc += ",rgbashift=rh=-7:bh=7:enable='lt(t,0.1)'"
    fc += f",fps={FPS},setsar=1,format=yuv420p[v]"
    return fc


def clean(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", (word or "").lower())


def find_punch(words: list[dict], punch_word: str, punch_rel: float | None) -> int:
    """Index of the punch word in whisper words (nearest match to Gemini's time), else last strong word."""
    target = clean(punch_word)
    cands = [i for i, w in enumerate(words) if target and clean(w["word"]) == target]
    if cands:
        if punch_rel is not None:
            return min(cands, key=lambda i: abs(words[i]["s"] - punch_rel))
        return cands[-1]
    if punch_rel is not None and words:
        near = [i for i, w in enumerate(words) if abs(w["s"] - punch_rel) < 2.5 and len(clean(w["word"])) >= 3]
        if near:
            return max(near, key=lambda i: len(clean(words[i]["word"])))
    for i in range(len(words) - 1, -1, -1):
        if len(clean(words[i]["word"])) >= 4:
            return i
    return len(words) - 1


def group_captions(words: list[dict], punch_idx: int, end_s: float) -> list[dict]:
    """1-4 word caption groups synced to whisper word timestamps."""
    groups, cur = [], []
    for i, w in enumerate(words):
        if w["s"] >= end_s:
            break
        if cur:
            prev = words[i - 1]
            chars = sum(len(x["word"]) for x in cur)
            if (len(cur) >= 4 or chars >= 18 or w["s"] - prev["e"] > 0.35
                    or re.search(r"[.,?!;:]$", prev["word"]) or i == punch_idx):
                groups.append(cur)
                cur = []
        cur.append({**w, "i": i})
        if i == punch_idx:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    for gi, g in enumerate(groups):
        nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else end_s
        start = g[0]["s"]
        end = min(nxt, g[-1]["e"] + 0.6, end_s)
        text = " ".join(x["word"] for x in g).strip()
        is_punch = any(x["i"] == punch_idx for x in g)
        italic = (not is_punch and len(g) <= 2 and clean(g[0]["word"]) in FILLERS) or text.endswith("...")
        key = max(range(len(g)), key=lambda k: len(clean(g[k]["word"])))
        stroke = -1
        if not is_punch and not italic:
            for k, x in enumerate(g):
                if clean(x["word"]) in IMPACT:
                    stroke = k
                    break
            if stroke < 0 and gi % 5 == 3 and len(clean(g[key]["word"])) >= 4:
                stroke = key
        out.append({
            "start": round(start, 3), "end": round(max(end, start + 0.2), 3),
            "words": [{"w": x["word"], "s": round(x["s"], 3), "e": round(x["e"], 3)} for x in g],
            "color": ACCENTS[gi % len(ACCENTS)], "italic": bool(italic), "key": key,
            "stroke": stroke, "punch": bool(is_punch),
        })
    return out


def montage_cuts(beats_comp: list[float], start: float, length: float) -> list[float]:
    """Cut lengths (s) on kicks from `start`, each 0.3-0.8s, total ~length."""
    bs = sorted(b for b in beats_comp if b > start + 0.05)
    cuts, t = [], start
    for b in bs:
        if t >= start + length:
            break
        d = b - t
        if d < 0.3:
            continue
        while d > 0.8:  # slow tempo: split evenly
            half = d / 2 if d / 2 >= 0.3 else 0.8
            cuts.append(half)
            t += half
            d = b - t
        if d >= 0.3:
            cuts.append(d)
            t = b
    while sum(cuts) < length - 0.3:
        cuts.append(0.45)
    return cuts


def good_hook(h: str) -> bool:
    h = (h or "").strip().strip('"').strip()
    return bool(h) and h.lower().rstrip(".!?") not in BANNED_HOOKS and len(h.split()) <= 6
