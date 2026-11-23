"""Montage shot inventory + selection (no repeats, story order, multi-source).

inventory():  one cheap ffmpeg pass per source (4 fps, 32x18 grey) -> camera shots -> <=2.5 s chunks, each with a
              64-bit dHash of its middle frame, a motion score and the source id.
select():     pure + unit-tested. Every chunk is used at most once, no two picks overlap (or sit closer than
              MIN_GAP s) in the same source, near-identical frames (dHash distance <= HASH_DUP) are never used
              twice, the dialogue window is blocked, and the picks are ordered with intent:
              intro = build-up in story order, post-drop = strongest shots with rising energy, best shot last.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import numpy as np

MIN_GAP = 1.0          # seconds between two picks taken from the same source
HASH_DUP = 10          # 64-bit dHash hamming distance <= this = the same-looking shot
CHUNK_S = 2.5          # long camera shots are split into chunks this long (each still needs its own look)
EDGE_S = 0.12          # trim off each side of a camera shot (no flash frames from the neighbour shot)
CUT_DIFF = 28.0        # mean abs grey difference between 0.25 s frames that marks a camera cut
DARK = 18.0            # mean luma below this = black / fade frame


@dataclass
class Chunk:
    src: str
    s: float
    e: float
    hash: int = 0
    motion: float = 0.0
    energy: float = 0.0        # Gemini 0-10 (0 = not picked by Gemini)
    kind: str = ""
    reason: str = ""
    shot: int = 0              # camera-shot index inside its source
    extra: dict = field(default_factory=dict)

    @property
    def length(self) -> float:
        return self.e - self.s

    def score(self) -> float:
        return 2.0 * self.energy + min(self.motion, 40.0) / 8.0


def hamming(a: int, b: int) -> int:
    return bin((a ^ b) & 0xFFFFFFFFFFFFFFFF).count("1")


def dhash(gray: np.ndarray) -> int:
    """64-bit difference hash of a small grey frame (any size)."""
    h, w = gray.shape
    ys = np.linspace(0, h, 9).astype(int)
    xs = np.linspace(0, w, 10).astype(int)
    m = np.array([[gray[ys[i]:max(ys[i] + 1, ys[i + 1]), xs[j]:max(xs[j] + 1, xs[j + 1])].mean()
                   for j in range(9)] for i in range(8)])
    bits = (m[:, 1:] > m[:, :-1]).flatten()
    return int(sum(1 << i for i, b in enumerate(bits) if b))


def read_gray(path, start: float, end: float, fps: int = 4, w: int = 32, h: int = 18, crop: str = ""):
    pre = f"crop={crop}," if crop else ""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{max(0.5, end - start):.2f}", "-i", str(path),
           "-vf", f"{pre}fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)


def chunks_from_frames(frames: np.ndarray, t0: float, fps: int, src: str,
                       blocked: list[tuple[float, float]] | None = None) -> list[Chunk]:
    """Pure: frames (n,h,w) sampled at fps from t0 -> chunks (shot-split, dark frames and blocked ranges dropped)."""
    n = len(frames)
    if n < 2:
        return []
    diffs = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2))
    cuts = [0] + [i + 1 for i, d in enumerate(diffs) if d > CUT_DIFF] + [n]
    out, shot = [], 0
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 2:
            continue
        shot += 1
        s, e = t0 + a / fps + EDGE_S, t0 + b / fps - EDGE_S
        k = max(1, int(round((e - s) / CHUNK_S)))
        step = (e - s) / k
        for j in range(k):
            cs, ce = s + j * step, s + (j + 1) * step
            fi = min(n - 1, int(round(((cs + ce) / 2 - t0) * fps)))
            fr = frames[fi]
            if fr.mean() < DARK:
                continue
            if blocked and any(cs < bb + MIN_GAP and ce > ba - MIN_GAP for ba, bb in blocked):
                continue
            i0, i1 = int((cs - t0) * fps), max(int((cs - t0) * fps) + 1, int((ce - t0) * fps))
            seg = diffs[i0:min(i1, len(diffs))]
            out.append(Chunk(src, round(cs, 3), round(ce, 3), dhash(fr), float(seg.mean()) if len(seg) else 0.0,
                             shot=shot))
    return out


def inventory(path, src: str, lo: float, hi: float, crop: str = "",
              blocked: list[tuple[float, float]] | None = None, fps: int = 4) -> list[Chunk]:
    frames = read_gray(path, lo, hi, fps=fps, crop=crop)
    return chunks_from_frames(frames, lo, fps, src, blocked)


def apply_gemini(chunks: list[Chunk], shots: list[dict], src: str) -> int:
    """Attach Gemini montage picks ({t, energy, kind, reason}) to the chunk that contains t."""
    hit = 0
    for sh in shots or []:
        try:
            t = float(sh.get("t"))
        except Exception:
            continue
        for c in chunks:
            if c.src == src and c.s - 0.3 <= t <= c.e + 0.3:
                en = float(sh.get("energy") or 6)
                if en > c.energy:
                    c.energy, c.kind, c.reason = en, str(sh.get("kind") or ""), str(sh.get("reason") or "")[:140]
                    hit += 1
                break
    return hit


def lazy_times(ts: list[float]) -> bool:
    """Gemini sometimes returns 0,1,2,3... instead of real picks: evenly spaced = not a real choice."""
    ts = sorted(float(t) for t in ts if isinstance(t, (int, float)))
    if len(ts) < 8:
        return False
    d = np.diff(ts)
    return float(np.mean(np.abs(d - np.median(d)) < 0.05)) > 0.7


class NotEnough(RuntimeError):
    def __init__(self, have: int, need: int):
        super().__init__(f"only {have} unique montage shots for {need} cuts")
        self.have, self.need = have, need


def _clash(c: Chunk, start: float, dur: float, used: list[tuple[str, float, float]], gap: float) -> bool:
    return any(u[0] == c.src and start < u[2] + gap and start + dur > u[1] - gap for u in used)


def unique_pool(chunks: list[Chunk], min_len: float, dup: int = HASH_DUP, min_score: float = 0.0) -> list[Chunk]:
    """Best-first chunks with no near-duplicate looks and no two chunks of the same camera shot unless they look
    different. Used to decide if a source has enough material."""
    out: list[Chunk] = []
    for c in sorted(chunks, key=lambda c: -c.score()):
        if c.length < min_len or c.score() < min_score:
            continue
        if any(hamming(c.hash, o.hash) <= dup for o in out):
            continue
        out.append(c)
    return out


def select(chunks: list[Chunk], intro_lens: list[float], outro_lens: list[float],
           blocked: list[tuple[str, float, float]] | None = None, gap: float = MIN_GAP, dup: int = HASH_DUP) -> list[dict]:
    """Pick one distinct chunk per cut. Returns [{src,start,dur,role,energy,kind,reason,hash}] (intro then outro).
    Raises NotEnough when the pool cannot fill every cut without repeats."""
    lens = list(intro_lens) + list(outro_lens)
    need = len(lens)
    used = list(blocked or [])
    free = [c for c in chunks if not _clash(c, c.s, c.length, used, gap)]
    pool = unique_pool(free, min(lens) if lens else 0.3, dup)
    if len(pool) < need:
        raise NotEnough(len(pool), need)
    # choose the best `need` chunks that can hold the cut lengths (longest cuts first get the longest chunks)
    chosen: list[Chunk] = []
    for c in pool:
        if len(chosen) >= need:
            break
        if not any(_clash(c, c.s, c.length, [(o.src, o.s, o.e)], gap) for o in chosen):
            chosen.append(c)
    if len(chosen) < need:
        raise NotEnough(len(chosen), need)
    # story order: intro = calmer build-up (lower energy) in source order; outro = payoff, rising, best last
    ranked = sorted(chosen, key=lambda c: c.score())
    intro = sorted(ranked[: len(intro_lens)], key=lambda c: (c.src, c.s))
    outro = ranked[len(intro_lens):]
    if len(outro) >= 3:                       # drop hit = 2nd best, finale = best, rising in between
        best, second = outro[-1], outro[-2]
        outro = [second] + outro[:-2] + [best]
    order = intro + outro
    # fit lengths: a slot longer than its chunk swaps with a later chunk that is long enough
    for i, L in enumerate(lens):
        if order[i].length + 1e-6 >= L:
            continue
        j = next((j for j in range(len(order)) if j != i and order[j].length + 1e-6 >= L
                  and order[i].length + 1e-6 >= lens[j]), None)
        if j is not None:
            order[i], order[j] = order[j], order[i]
    # never two cuts in a row from the same camera shot / neighbouring seconds of one source
    for i in range(1, len(order)):
        a, b = order[i - 1], order[i]
        if a.src == b.src and (a.shot == b.shot or abs(a.s - b.s) < 3.0):
            for j in range(i + 1, len(order)):
                c = order[j]
                if not (c.src == a.src and (c.shot == a.shot or abs(c.s - a.s) < 3.0)) \
                        and c.length + 1e-6 >= lens[i] and b.length + 1e-6 >= lens[j]:
                    order[i], order[j] = order[j], order[i]
                    break
    picks = []
    for i, (c, L) in enumerate(zip(order, lens)):
        start = c.s + max(0.0, (c.length - L) / 2)
        if c.length + 1e-6 < L:               # still too short: extend into the following frames of the source
            start = c.s
        if _clash(c, start, L, used, gap):
            raise NotEnough(i, need)
        used.append((c.src, start, start + L))
        picks.append({"src": c.src, "start": round(start, 3), "dur": round(L, 3),
                      "role": "intro" if i < len(intro_lens) else "montage", "energy": c.energy, "kind": c.kind,
                      "reason": c.reason, "hash": c.hash, "shot": c.shot})
    return picks


def audit(picks: list[dict], gap: float = MIN_GAP, dup: int = HASH_DUP) -> list[str]:
    """Problems in a pick list (used as a hard local QC check)."""
    issues = []
    for i in range(len(picks)):
        for j in range(i + 1, len(picks)):
            a, b = picks[i], picks[j]
            if a["src"] == b["src"] and a["start"] < b["start"] + b["dur"] + gap - 1e-6 \
                    and b["start"] < a["start"] + a["dur"] + gap - 1e-6:
                issues.append(f"overlap {i}/{j} {a['src']}@{a['start']:.1f}/{b['start']:.1f}")
            if hamming(int(a["hash"]), int(b["hash"])) <= dup:
                issues.append(f"repeat look {i}/{j}")
    return issues
