"""Montage selection tests: no repeats, no overlaps, min gap, near-duplicate looks, story order, multi-source.
Run: python -m pytest tests  (or python tests/test_montage.py)."""
import importlib.util
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("montage_select", ROOT / "pipeline_lib" / "montage_select.py")
M = importlib.util.module_from_spec(_spec)
sys.modules["montage_select"] = M
_spec.loader.exec_module(M)


def _rand_hash(rng):
    return rng.getrandbits(64)


def _chunks(src, n, rng, start=20.0, step=3.0, length=2.0, energy=None, hashes=None):
    out = []
    for i in range(n):
        s = start + i * step
        out.append(M.Chunk(src, s, s + length, hashes[i] if hashes else _rand_hash(rng),
                           motion=rng.uniform(2, 30), energy=(energy if energy is not None else rng.uniform(0, 9)),
                           shot=i + 1))
    return out


LENS_I = [0.94, 0.94, 0.94, 0.47, 0.47, 0.94, 0.94, 0.94, 0.47]
LENS_O = [0.47] * 4 + [0.47, 0.47, 0.94, 0.47] * 6


def test_no_repeat_no_overlap_min_gap():
    rng = random.Random(1)
    ch = _chunks("main", 60, rng)
    picks = M.select(ch, LENS_I, LENS_O)
    assert len(picks) == len(LENS_I) + len(LENS_O)
    assert M.audit(picks) == []
    for i, a in enumerate(picks):
        for b in picks[i + 1:]:
            if a["src"] == b["src"]:
                gap = max(b["start"] - (a["start"] + a["dur"]), a["start"] - (b["start"] + b["dur"]))
                assert gap >= M.MIN_GAP - 1e-6
    assert [p["dur"] for p in picks] == [round(x, 3) for x in LENS_I + LENS_O]


def test_near_duplicate_looks_are_dropped():
    rng = random.Random(2)
    base = _rand_hash(rng)
    # 40 chunks that all look the same (talking head) + 10 distinct ones -> only 11 unique looks
    hashes = [base ^ (1 << (i % 5)) for i in range(40)] + [_rand_hash(rng) for _ in range(10)]
    ch = _chunks("main", 50, rng, hashes=hashes)
    pool = M.unique_pool(ch, 0.4)
    assert len(pool) == 11
    try:
        M.select(ch, LENS_I, LENS_O)
    except M.NotEnough as e:
        assert e.have == 11
    else:
        raise AssertionError("must ask for more footage instead of repeating a shot")


def test_adjacent_chunks_of_one_shot_not_both_used():
    rng = random.Random(3)
    # chunks 2.5 s apart without a gap: picking both would put two cuts < MIN_GAP apart
    ch = [M.Chunk("main", 10 + i * 2.5, 12.5 + i * 2.5, _rand_hash(rng), 10, 5, shot=1) for i in range(20)]
    pool = M.unique_pool(ch, 0.4)
    try:
        picks = M.select(pool, [0.5] * 6, [0.5] * 6)
    except M.NotEnough:
        return
    assert M.audit(picks) == []


def test_blocked_dialogue_window_never_used():
    rng = random.Random(4)
    ch = _chunks("main", 60, rng, start=0.0, step=3.0)
    picks = M.select(ch, LENS_I, LENS_O, blocked=[("main", 30.0, 45.0)])
    for p in picks:
        assert not (p["src"] == "main" and p["start"] < 46.0 and p["start"] + p["dur"] > 29.0), p


def test_multi_source_fills_what_main_lacks():
    rng = random.Random(5)
    main = _chunks("main", 15, rng)
    try:
        M.select(main, LENS_I, LENS_O)
        raise AssertionError("15 shots cannot fill 33 cuts")
    except M.NotEnough:
        pass
    extra = _chunks("x1", 30, rng, start=5.0)
    picks = M.select(main + extra, LENS_I, LENS_O)
    srcs = {p["src"] for p in picks}
    assert srcs == {"main", "x1"} and M.audit(picks) == []


def test_story_order_and_rising_energy():
    rng = random.Random(6)
    ch = _chunks("main", 60, rng)
    picks = M.select(ch, LENS_I, LENS_O)
    intro = picks[:len(LENS_I)]
    outro = picks[len(LENS_I):]
    score = {(c.src, c.s): c.score() for c in ch}
    def sc(p):
        return max(v for (s, a), v in score.items() if s == p["src"] and a - 0.01 <= p["start"] <= a + 2.5)
    assert max(sc(p) for p in intro) <= max(sc(p) for p in outro)
    assert sc(outro[-1]) == max(sc(p) for p in picks)       # best shot is the finale


def test_no_back_to_back_same_shot():
    rng = random.Random(7)
    ch = []
    for shot in range(30):   # 2 chunks per camera shot, different looks
        ch.append(M.Chunk("main", shot * 8.0, shot * 8.0 + 2.4, _rand_hash(rng), 10, rng.uniform(0, 9), shot=shot))
        ch.append(M.Chunk("main", shot * 8.0 + 4.0, shot * 8.0 + 6.4, _rand_hash(rng), 10, rng.uniform(0, 9), shot=shot))
    picks = M.select(ch, LENS_I, LENS_O)
    for a, b in zip(picks, picks[1:]):
        assert not (a["src"] == b["src"] and a["shot"] == b["shot"]), (a, b)


def test_lazy_gemini_times_detected():
    assert M.lazy_times([float(i) for i in range(40)])
    assert not M.lazy_times([3.2, 9.8, 15.1, 27.4, 33.0, 41.7, 58.2, 63.9, 80.5])


def test_chunks_from_frames_split_and_dark():
    fps = 4
    rng = np.random.default_rng(0)
    a = rng.uniform(60, 200, (18, 32)).astype(np.float32)
    b = rng.uniform(60, 200, (18, 32)).astype(np.float32)
    dark = np.full((18, 32), 5, np.float32)
    frames = np.stack([a] * 20 + [b] * 12 + [dark] * 8)     # shot A 5 s, shot B 3 s, black 2 s
    ch = M.chunks_from_frames(frames, 10.0, fps, "main")
    shots = {c.shot for c in ch}
    assert len(shots) >= 2
    assert all(c.s >= 10.0 and c.e <= 20.0 for c in ch)
    assert all(c.e <= 18.0 + 1e-6 for c in ch)             # no chunk from the black tail
    assert M.hamming(ch[0].hash, ch[-1].hash) > M.HASH_DUP  # A and B look different


def test_apply_gemini_marks_chunks():
    rng = random.Random(8)
    ch = _chunks("main", 10, rng, energy=0.0)
    n = M.apply_gemini(ch, [{"t": 21.0, "energy": 9, "kind": "hero", "reason": "punch"}], "main")
    assert n == 1 and ch[0].energy == 9 and ch[0].kind == "hero"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
