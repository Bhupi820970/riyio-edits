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
         "unsharp=5:5:1.0:5:5:0.0,noise=alls=7:allf=t")   # light moving film grain like ref1/ref2

# Reference look (idea 4): light colour split only on the hit cuts (drop + hero shots), first ~0.12 s.
RGB_SPLIT = "rgbashift=rh=-4:bh=4:rv=1:bv=-1:enable='lt(t,0.12)'"
# RIYIO watermark (BiBi, Nov 24): about half the old size (0.07 of the frame width) and glass-like.
WM_FRAC = 0.035
WM_OPACITY = 0.3
# Opening hook / question captions ("WHAT DO YOU THINK..?") are removed for good (BiBi, Nov 24).
INTRO_QUESTION_KEYS = ("hook_question", "hookQuestion", "question", "intro_caption", "opening_caption")


def frame_filter(rgb_split: bool = False, crop: str = "") -> str:
    """crop = 'w:h:x:y' of the real picture inside baked-in letterbox bars (from detect_letterbox)."""
    pre = f"crop={crop}," if crop else ""
    fc = (f"[0:v]{pre}split=2[a][b];"
          f"[a]scale=270:338:force_original_aspect_ratio=increase,crop=270:338,boxblur=12:2,"
          f"eq=brightness=-0.12:saturation=0.75,scale={W}:{H}[bg];"
          f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{GRADE}")
    if rgb_split:
        fc += "," + RGB_SPLIT
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


def group_captions(words: list[dict], punch_idx: int, end_s: float, max_words: int = 4) -> list[dict]:
    """1-4 word caption groups synced to whisper word timestamps."""
    groups, cur = [], []
    for i, w in enumerate(words):
        if w["s"] >= end_s:
            break
        if cur:
            prev = words[i - 1]
            chars = sum(len(x["word"]) for x in cur)
            if (len(cur) >= max_words or chars >= 18 or w["s"] - prev["e"] > 0.35
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
            "raw": g,
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



# ---------------------------------------------------------------- pro-edit (Vice Cartel) timeline
# Measured from the reference edit https://youtu.be/ieltf77ofiA (pro-edit vicestyle.py, ~128 BPM):
#   0-12.0s intro montage (music 100%, cuts on 1-2 beats) -> 12-41.7s dialogue (music ducked, speaker-side
#   captions) -> drop on the last punch word -> 41.7-52s fast montage (1-2 beat cuts) to the end.
INTRO_TARGET_S = 9.0          # intro montage (beats, music full)
INTRO_MIN_S, INTRO_MAX_S = 6.0, 12.5
OUTRO_MIN_S = 9.0             # fast montage after the drop
TIMELINE_TARGET_S = 42.0
TIMELINE_MIN_S, TIMELINE_MAX_S = 35.0, 59.0
HOOK_PAT = [2, 2, 2, 1, 1, 2]     # vicestyle.py hook_pat (in beat units)
END_PAT = [1, 1, 2, 1]            # vicestyle.py end_pat
MIN_CUT_S = 0.35


def beat_unit(ibi: float) -> int:
    """1 beat per unit, or 2 on very fast songs so no cut is shorter than ~0.42s."""
    return 1 if ibi >= 0.42 else 2


def median_ibi(beats: list[float], default: float = 0.5) -> float:
    bs = sorted(beats)
    d = sorted(bs[i + 1] - bs[i] for i in range(len(bs) - 1) if bs[i + 1] - bs[i] > 0.15)
    ibi = d[len(d) // 2] if d else default
    return min(max(ibi, 0.25), 1.5)


def subdivide_slow(beats: list[float], slow: float = 0.75) -> list[float]:
    """librosa often locks onto half-time (e.g. 61 BPM for a 122 BPM track -> ~1-2 s cuts, too slow vs the refs).
    When beats are > `slow` s apart, add the half-beats so cuts land on 0.4-1.0 s like the reference edits."""
    sb = sorted(beats)
    if len(sb) < 4 or median_ibi(sb) <= slow:
        return sb
    mids = [(sb[i] + sb[i + 1]) / 2 for i in range(len(sb) - 1)]
    return sorted(sb + mids)


def beat_cuts(grid: list[float], start: float, end: float, pattern: list[int], unit: int,
              flurry: int = 0) -> list[tuple[float, str]]:
    """Hard cuts on `grid` (video-time beats) from start to end. Pattern is in beat units;
    the first `flurry` cuts are single units (rapid hits right after the drop)."""
    g = sorted(b for b in grid if start + 0.05 < b < end + 8.0)
    ibi = median_ibi(g) if len(g) > 2 else 0.5
    while not g or g[-1] < end + 2 * ibi:   # extend past the song's detected beats if needed
        g.append((g[-1] if g else start) + ibi)
    g = [start] + g
    out, k, n, t = [], 0, 0, start
    while t < end - 1e-3:
        steps = unit if n < flurry else pattern[(n - flurry) % len(pattern)] * unit
        k2 = min(len(g) - 1, k + steps)
        d = g[k2] - t
        if d < MIN_CUT_S:                      # odd grid gap: take one more beat
            k2 = min(len(g) - 1, k2 + 1)
            d = g[k2] - t
        if end - (t + d) < MIN_CUT_S:          # never leave a sliver at the end
            d = end - t
        if d <= 1e-3:
            break
        out.append((round(d, 3), "flurry" if n < flurry else "beat"))
        t += d
        k = k2
        n += 1
    return out


def plan_timeline(song_beats: list[float], song_drop: float, song_len: float, dlg_len: float,
                  punch_rel: float, target: float = TIMELINE_TARGET_S) -> dict:
    """pro-edit timeline: intro montage -> dialogue (punch at punch_rel inside it) -> drop -> montage.
    song_beats / song_drop / song_len are song seconds; dlg_len = dialogue length (ends after the punch word);
    punch_rel = punch word start inside the dialogue. The song plays continuously from `song_start`, so the
    drop beat lands exactly on the punch word. Raises ValueError if it cannot fit 35-59s."""
    if dlg_len <= punch_rel:
        raise ValueError("punch must be inside the dialogue")
    sb = sorted(b for b in song_beats if b >= 0)
    sb = subdivide_slow(sb)
    ibi = median_ibi(sb)
    unit = beat_unit(ibi)
    # intro: video 0 and the punch word (drop) are both on the beat grid -> intro + punch_rel = n beats.
    # (run_v2 also nudges the dialogue lead so punch_rel ~ whole beats, then the cut into the dialogue is on a beat too)
    n = max(1, int(round((INTRO_TARGET_S + punch_rel) / ibi)))
    intro = n * ibi - punch_rel
    while intro < INTRO_MIN_S:
        intro += ibi
    while intro > INTRO_MAX_S and intro - ibi >= INTRO_MIN_S:
        intro -= ibi
    # keep the dialogue in the middle and the whole video inside 35-59s
    outro = max(OUTRO_MIN_S, target - intro - dlg_len)
    if intro + dlg_len + outro < TIMELINE_MIN_S:
        outro = TIMELINE_MIN_S + 0.5 - intro - dlg_len
    if intro + dlg_len + outro > TIMELINE_MAX_S:
        outro = TIMELINE_MAX_S - 0.3 - intro - dlg_len
        if outro < OUTRO_MIN_S * 0.6:
            raise ValueError(f"dialogue {dlg_len:.1f}s too long for {TIMELINE_MAX_S:.0f}s")
    P = intro + punch_rel                      # punch word (= drop) in video time
    total = intro + dlg_len + outro
    # song anchor: a beat >= the detected drop (and >= P so the song starts at >= 0s)
    # (falls back to any beat >= P when the detected drop sits too late in the song)
    cands = [b for b in sb if b >= max(song_drop - 1e-3, P)] + [b for b in sb if P <= b < song_drop - 1e-3]
    drop_b = None
    for b in cands:
        if b - P + total <= song_len - 0.2:
            drop_b = b
            break
    if drop_b is None:
        raise ValueError("song too short for this timeline")
    S = drop_b - P                             # song second at video 0
    grid = [b - S for b in sb if b - S > -1e-3]
    intro_cuts = beat_cuts(grid, 0.0, intro, HOOK_PAT, unit)
    D_end = intro + dlg_len
    outro_cuts = beat_cuts(grid, D_end, total, END_PAT, unit, flurry=4)
    return {"ibi": round(ibi, 4), "unit": unit, "intro_s": round(intro, 3), "dialogue_start_s": round(intro, 3),
            "dialogue_end_s": round(D_end, 3), "drop_s": round(P, 3), "total_s": round(total, 3),
            "song_start": round(S, 3), "song_drop_beat": round(drop_b, 3),
            "intro_cuts": intro_cuts, "outro_cuts": outro_cuts}


def good_hook(h: str) -> bool:
    h = (h or "").strip().strip('"').strip()
    return bool(h) and h.lower().rstrip(".!?") not in BANNED_HOOKS and len(h.split()) <= 6


def parse_cropdetect(stderr: str, src_w: int, src_h: int) -> str:
    """Most common cropdetect result; only used when it removes black letterbox bars (>4% of height)."""
    from collections import Counter
    found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", stderr or "")
    if not found:
        return ""
    w, h, x, y = (int(v) for v in Counter(found).most_common(1)[0][0])
    if w < src_w * 0.9 or h < src_h * 0.5 or h > src_h * 0.96:
        return ""  # not a clean letterbox -> keep the full frame (never crop the picture)
    return f"{w}:{h}:{x}:{y}"


def strip_intro_question(plan: dict) -> dict:
    """Remove every opening question / hook caption the director might still return (never rendered)."""
    for k in INTRO_QUESTION_KEYS:
        plan.pop(k, None)
    return plan
