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
    assert sc(outro[0]) == max(sc(p) for p in picks)        # strongest shot sits ON the drop (punch word)


def test_hero_cuts_get_next_strongest_and_are_marked_hits():
    rng = random.Random(9)
    ch = _chunks("main", 60, rng)
    picks = M.select(ch, LENS_I, LENS_O)
    outro = picks[len(LENS_I):]
    heroes = M.hero_slots(LENS_O)
    assert heroes and 0 not in heroes and len(LENS_O) - 1 not in heroes
    assert all(LENS_O[h] == max(LENS_O[1:-1]) for h in heroes)          # hero = the longer beat holds
    hit_idx = [i for i, p in enumerate(outro) if p["hit"]]
    assert hit_idx == [0] + heroes
    assert not any(p["hit"] for p in picks[:len(LENS_I)])
    others = [p["score"] for i, p in enumerate(outro) if not p["hit"]]
    assert min(p["score"] for p in outro if p["hit"]) >= max(others) - 1e-6   # hits = the strongest shots
    assert M.audit(picks) == []


def test_arrange_outro_pure():
    cs = [M.Chunk("main", i * 5.0, i * 5.0 + 2, i, energy=float(i)) for i in range(10)]
    out = M.arrange_outro(cs, 10, [3, 6])
    e = [c.energy for c in out]
    assert e[0] == 9 and e[3] == 8 and e[6] == 7 and e[-1] == 6
    rest = [x for i, x in enumerate(e) if i not in (0, 3, 6, 9)]
    assert rest == sorted(rest)                                          # rising in between


def _band_noise(rng, n, sr, lo, hi, amp):
    x = rng.standard_normal(n)
    f = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1 / sr)
    f[(fr < lo) | (fr > hi)] = 0
    y = np.fft.irfft(f, n)
    return (amp * y / (np.abs(y).max() + 1e-9)).astype(np.float32)


def test_loudness_scores_peak_vs_quiet():
    sr = M.AUDIO_SR
    rng = np.random.default_rng(1)
    sig = _band_noise(rng, sr * 10, sr, 20, 7000, 0.02)
    sig[sr * 6: sr * 7] += _band_noise(rng, sr, sr, 30, 90, 0.8)          # explosion at 6-7 s (sub-bass)
    sc = M.loudness_scores(sig, sr, 100.0, [(101.0, 103.0), (105.8, 107.2), (108.0, 109.5)])
    assert sc[1] >= 9.0 and sc[0] <= 2.0 and sc[2] <= 2.0
    assert M.loudness_scores(np.zeros(10, np.float32), sr, 0.0, [(0, 1)]) == [0.0]


def test_loud_speech_is_ignored_effects_count():
    """A man shouting (voice band, syllable-modulated, LOUDER) scores ~0; a quieter gunshot / impact scores high."""
    sr = M.AUDIO_SR
    rng = np.random.default_rng(2)
    n = sr * 12
    sig = _band_noise(rng, n, sr, 20, 7000, 0.01)
    t = np.arange(sr * 4) / sr
    speech = _band_noise(rng, sr * 4, sr, 350, 3000, 1.0) * (0.55 + 0.45 * np.sin(2 * np.pi * 4.5 * t)).astype(np.float32)
    sig[sr * 2: sr * 6] += speech                                           # shouting 2-6 s
    boom = _band_noise(rng, sr // 2, sr, 30, 100, 0.2) + _band_noise(rng, sr // 2, sr, 4500, 7500, 0.12)
    sig[sr * 9: sr * 9 + sr // 2] += boom                                   # gunshot / impact at 9 s
    sc = M.loudness_scores(sig, sr, 0.0, [(2.5, 5.5), (8.9, 9.6), (10.5, 11.5)])
    assert float(np.sqrt(np.mean(speech ** 2))) > float(np.sqrt(np.mean(boom ** 2)))   # speech is louder overall
    assert sc[0] <= 2.0, sc
    assert sc[1] >= 8.0, sc
    fx, share = M.band_profile(sig, sr)
    assert share[30] > M.SPEECH_SHARE and share[92] < M.SPEECH_SHARE


def test_motion_floor_drops_static_shots_unless_gemini_rates_them():
    still = M.Chunk("main", 0, 2, 0x0F0F0F0F0F0F0F0F, motion=0.5, energy=0.0)
    reveal = M.Chunk("main", 5, 7, 0xF0F0F0F0F0F0F0F0, motion=0.5, energy=8.0)
    moving = M.Chunk("main", 10, 12, 0x00FF00FF00FF00FF, motion=6.0, energy=0.0)
    assert not M.eligible(still) and M.eligible(reveal) and M.eligible(moving)
    pool = M.unique_pool([still, reveal, moving], 0.4)
    assert still not in pool and reveal in pool and moving in pool
    rng = random.Random(11)
    ch = _chunks("main", 90, rng)
    for c in ch[::2]:
        c.motion, c.energy = 0.3, 0.0                                       # half the shots are talking heads
    picks = M.select(ch, LENS_I, LENS_O)
    statics = {(c.src, c.shot) for c in ch[::2]}
    assert not any((p["src"], p["shot"]) in statics for p in picks)


def test_loudness_alone_is_not_strong_and_triggers_extra():
    loud_only = [M.Chunk("main", i * 4.0, i * 4.0 + 2, i, motion=3.0, energy=0.0, loud=10.0, shot=i) for i in range(40)]
    assert not any(M.is_strong(c) for c in loud_only)
    yes, why = M.needs_extra(loud_only, 30)
    assert yes and "strong" in why
    rated = [M.Chunk("main", i * 4.0, i * 4.0 + 2, i, motion=13.0, energy=0.0, shot=i) for i in range(40)]
    yes, why = M.needs_extra(rated, 30)                                     # moving, but Gemini rated nothing
    assert yes and "Gemini" in why
    good = [M.Chunk("main", i * 4.0, i * 4.0 + 2, i, motion=13.0, energy=6.0, shot=i) for i in range(40)]
    assert M.needs_extra(good, 30) == (False, "enough")
    assert M.needs_extra(good, 30, sufficient=False)[0]
    assert M.needs_extra(good[:20], 30)[0]


def test_pipeline_wiring_for_extras_and_floor():
    run = (ROOT / "run_v2.py").read_text()
    assert "msel.needs_extra(pool, need" in run and "c.loud >= 7" not in run
    assert "min_motion=0.0" in run                                          # relaxed only as a last resort


def test_loud_shot_wins_on_the_drop():
    rng = random.Random(10)
    ch = _chunks("main", 50, rng, energy=5.0)
    for c in ch:
        c.motion = 10.0
    ch[17].loud = 10.0                           # the gunshot / impact moment
    picks = M.select(ch, LENS_I, LENS_O)
    drop = picks[len(LENS_I)]
    assert abs(drop["start"] - ch[17].s) < 1.0 and drop["loud"] == 10.0


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
