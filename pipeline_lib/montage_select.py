"""Montage shot inventory + selection (no repeats, story order, multi-source).

inventory():  one cheap ffmpeg pass per source (4 fps, 32x18 grey) -> camera shots -> <=2.5 s chunks, each with a
              64-bit dHash of its middle frame, a motion score and the source id.
select():     pure + unit-tested. Every chunk is used at most once, no two picks overlap (or sit closer than
              MIN_GAP s) in the same source, near-identical frames (dHash distance <= HASH_DUP) are never used
              twice, the dialogue window is blocked, and the picks are ordered with intent:
              intro = build-up in story order; post-drop = the STRONGEST shot right on the drop (punch word),
              the next strongest on the hero cuts (the longer beat cuts), rising energy, 2nd best as the finale.
Energy by sound (idea 2): every chunk also gets `loud` (0-10) from the source's own music / effects energy (sub-bass
              + high band, speech-dominated windows ignored), so gunshots, impacts and roars rank higher but people
              talking loudly do not. Loudness only ranks; it never makes a shot "strong" on its own (is_strong).
Motion floor: static shots (motion < MIN_MOTION) are not used in the montages unless Gemini rated them >= 7.
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
    loud: float = 0.0          # 0-10 audio RMS peak of the source under this chunk (energy by sound)
    extra: dict = field(default_factory=dict)

    @property
    def length(self) -> float:
        return self.e - self.s

    def score(self) -> float:
        return 2.0 * self.energy + min(self.motion, 40.0) / 8.0 + LOUD_W * min(self.loud, 10.0)


LOUD_W = 0.4           # weight of the sound energy (0-10 -> up to +4, like motion's up to +5)
AUDIO_SR = 16000
MIN_MOTION = 2.0       # mean grey frame difference; talking heads / static frames sit at ~0.2-1.5
STATIC_OK_ENERGY = 7.0 # Gemini energy that lets a static shot (a reveal, a stare) in anyway
SPEECH_SHARE = 0.72    # window energy share in the 300-3400 Hz voice band above this = speech, not music / effects
LOW_HZ, HIGH_HZ = 110.0, 4000.0
STRONG_ENERGY, STRONG_MOTION = 5.0, 12.0
GEMINI_MIN_RATED = 0.4 # if fewer than 40% of the unique shots carry a Gemini rating, fetch related videos


def eligible(c: "Chunk", min_motion: float = MIN_MOTION) -> bool:
    """Montage-worthy: moving enough, or a static shot Gemini rated very strong."""
    return c.motion >= min_motion or c.energy >= STATIC_OK_ENERGY


def is_strong(c: "Chunk") -> bool:
    """Strong shot = Gemini energy or clear motion. Loudness alone never counts."""
    return c.energy >= STRONG_ENERGY or c.motion >= STRONG_MOTION


def needs_extra(pool: list["Chunk"], need: int, sufficient=None) -> tuple[bool, str]:
    """Pure: should the montage fetch 1-2 related videos? Returns (yes, why)."""
    strong = sum(1 for c in pool if is_strong(c))
    rated = sum(1 for c in pool if c.energy > 0)
    if len(pool) < need:
        return True, f"only {len(pool)} unique shots for {need} cuts"
    if strong < int(0.6 * need):
        return True, f"only {strong} strong shots (need {int(0.6 * need)})"
    if pool and rated < GEMINI_MIN_RATED * min(len(pool), need):
        return True, f"Gemini rated only {rated} of {len(pool)} shots (energy mostly 0)"
    if sufficient is False:
        return True, "director says this clip alone is not enough"
    return False, "enough"


def read_audio(path, start: float, end: float, sr: int = AUDIO_SR) -> np.ndarray:
    """Mono float samples of the source audio (cheap 8 kHz ffmpeg pass); empty if the source has no audio."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{max(0.5, end - start):.2f}", "-i", str(path),
           "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw[: len(raw) // 2 * 2], np.int16).astype(np.float32) / 32768.0


def band_profile(samples: np.ndarray, sr: int, win: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """Pure: per 100 ms window -> (music/effects energy = RMS of the sub-bass + high band, voice-band share 0-1)."""
    n = int(sr * win)
    k = len(samples) // n
    if k < 2:
        return np.zeros(0, np.float32), np.zeros(0, np.float32)
    fr = np.fft.rfftfreq(n, 1.0 / sr)
    low, high = fr < LOW_HZ, fr > HIGH_HZ
    voice = (fr >= 300) & (fr <= 3400)
    fx, share = np.zeros(k, np.float32), np.zeros(k, np.float32)
    win_fn = np.hanning(n).astype(np.float32)
    for a in range(0, k, 1000):                      # blocks keep memory small on long sources
        b = min(k, a + 1000)
        spec = np.abs(np.fft.rfft(samples[a * n: b * n].reshape(b - a, n) * win_fn, axis=1)) ** 2
        tot = spec.sum(axis=1) + 1e-12
        fx[a:b] = np.sqrt((spec[:, low].sum(axis=1) + spec[:, high].sum(axis=1)) / n)
        share[a:b] = spec[:, voice].sum(axis=1) / tot
    return fx, share


def loudness_scores(samples: np.ndarray, sr: int, t0: float, spans: list[tuple[float, float]],
                    win: float = 0.1) -> list[float]:
    """Pure: 0-10 music / effects loudness per span = 90th percentile of the non-speech energy inside the span,
    scaled against the whole source. Speech-dominated windows count as 0, so loud talking never scores high."""
    if samples is None or len(samples) < sr * win * 2:
        return [0.0] * len(spans)
    fx, share = band_profile(samples, sr, win)
    k = len(fx)
    fx = np.where(share > SPEECH_SHARE, 0.0, fx)
    lo, hi = float(np.percentile(fx, 10)), float(np.percentile(fx, 99))
    if hi - lo < 1e-9:
        return [0.0] * len(spans)
    out = []
    for s, e in spans:
        a, b = max(0, int((s - t0) / win)), min(k, max(int((s - t0) / win) + 1, int((e - t0) / win)))
        seg = fx[a:b]
        v = float(np.percentile(seg, 90)) if len(seg) else lo
        out.append(round(float(np.clip((v - lo) / (hi - lo), 0.0, 1.0)) * 10.0, 2))
    return out


def apply_loudness(chunks: list["Chunk"], samples: np.ndarray, sr: int, t0: float) -> None:
    for c, v in zip(chunks, loudness_scores(samples, sr, t0, [(c.s, c.e) for c in chunks])):
        c.loud = v


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
    chunks = chunks_from_frames(frames, lo, fps, src, blocked)
    try:
        apply_loudness(chunks, read_audio(path, lo, hi), AUDIO_SR, lo)
    except Exception as e:  # no audio track / ffmpeg hiccup: motion + Gemini energy still rank the shots
        print("sound energy skipped:", repr(e)[:120], flush=True)
    return chunks


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


def unique_pool(chunks: list[Chunk], min_len: float, dup: int = HASH_DUP, min_score: float = 0.0,
                min_motion: float = MIN_MOTION) -> list[Chunk]:
    """Best-first chunks with no near-duplicate looks and no two chunks of the same camera shot unless they look
    different. Used to decide if a source has enough material."""
    out: list[Chunk] = []
    for c in sorted(chunks, key=lambda c: -c.score()):
        if c.length < min_len or c.score() < min_score or not eligible(c, min_motion):
            continue
        if any(hamming(c.hash, o.hash) <= dup for o in out):
            continue
        out.append(c)
    return out


def select(chunks: list[Chunk], intro_lens: list[float], outro_lens: list[float],
           blocked: list[tuple[str, float, float]] | None = None, gap: float = MIN_GAP, dup: int = HASH_DUP,
           min_motion: float = MIN_MOTION) -> list[dict]:
    """Pick one distinct chunk per cut. Returns [{src,start,dur,role,energy,kind,reason,hash}] (intro then outro).
    Raises NotEnough when the pool cannot fill every cut without repeats."""
    lens = list(intro_lens) + list(outro_lens)
    need = len(lens)
    used = list(blocked or [])
    free = [c for c in chunks if not _clash(c, c.s, c.length, used, gap)]
    pool = unique_pool(free, min(lens) if lens else 0.3, dup, min_motion=min_motion)
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
    # story order: intro = calmer build-up (lower energy) in source order; outro = payoff with the strongest
    # shot ON the drop, the next strongest on the hero cuts, rising energy in between, 2nd best as the finale
    ranked = sorted(chosen, key=lambda c: c.score())
    intro = sorted(ranked[: len(intro_lens)], key=lambda c: (c.src, c.s))
    outro_ranked = ranked[len(intro_lens):]
    heroes = hero_slots(list(outro_lens))
    outro = arrange_outro(outro_ranked, len(outro_lens), heroes)
    order = intro + outro
    n_in = len(intro_lens)
    protected = {n_in} | {n_in + h for h in heroes}
    # fit lengths: a slot longer than its chunk swaps with a later chunk that is long enough
    for i, L in enumerate(lens):
        if order[i].length + 1e-6 >= L:
            continue
        j = next((j for j in range(len(order)) if j != i and j not in protected and order[j].length + 1e-6 >= L
                  and order[i].length + 1e-6 >= lens[j]), None)
        if j is not None:
            order[i], order[j] = order[j], order[i]
    # never two cuts in a row from the same camera shot / neighbouring seconds of one source
    for i in range(1, len(order)):
        a, b = order[i - 1], order[i]
        if i == n_in:                          # the dialogue sits between the intro and the drop
            continue
        if i in protected:                     # keep the strong shot on its slot, move the neighbour instead
            if a.src == b.src and (a.shot == b.shot or abs(a.s - b.s) < 3.0) and (i - 1) not in protected:
                for j in range(i + 1, len(order)):
                    c = order[j]
                    if j not in protected and not (c.src == b.src and (c.shot == b.shot or abs(c.s - b.s) < 3.0)) \
                            and c.length + 1e-6 >= lens[i - 1] and a.length + 1e-6 >= lens[j]:
                        order[i - 1], order[j] = order[j], order[i - 1]
                        break
            continue
        if a.src == b.src and (a.shot == b.shot or abs(a.s - b.s) < 3.0):
            for j in range(i + 1, len(order)):
                c = order[j]
                if j not in protected and not (c.src == a.src and (c.shot == a.shot or abs(c.s - a.s) < 3.0)) \
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
                      "reason": c.reason, "hash": c.hash, "shot": c.shot, "loud": c.loud,
                      "motion": round(c.motion, 2), "score": round(c.score(), 2),
                      "hit": i in protected})       # drop + hero cuts get the hit SFX / RGB split
    return picks


def hero_slots(outro_lens: list[float], frac: float = 6.0) -> list[int]:
    """Pure: outro slot indices (not the drop slot 0, not the finale) of the hero cuts = the longest beat cuts
    (the 2-beat holds of the END pattern), about one in six cuts, at least 2, earliest first on ties."""
    n = len(outro_lens)
    if n < 4:
        return []
    k = max(2, int(round(n / frac)))
    idx = sorted(range(1, n - 1), key=lambda i: (-outro_lens[i], i))[:k]
    return sorted(idx)


def arrange_outro(ranked_low_to_high: list[Chunk], n: int, heroes: list[int]) -> list[Chunk]:
    """Pure: slot 0 (drop / punch word) = strongest, hero slots = next strongest (in time order), finale = the
    best of the rest, all other slots rising in energy."""
    best_first = list(reversed(ranked_low_to_high[:n]))
    if n < 3:
        return best_first
    out: list[Chunk | None] = [None] * n
    out[0] = best_first.pop(0)
    for h in heroes:
        out[h] = best_first.pop(0)
    out[n - 1] = best_first.pop(0)
    rest = sorted(best_first, key=lambda c: c.score())
    for i in range(n):
        if out[i] is None:
            out[i] = rest.pop(0)
    return out  # type: ignore[return-value]


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
