"""Unit tests for the pro-edit timeline planner (intro montage -> dialogue -> drop -> montage).
Run: python -m pytest tests  (or python tests/test_timeline.py)."""
import importlib.util
import itertools
from pathlib import Path

_spec = importlib.util.spec_from_file_location("style", Path(__file__).resolve().parents[1] / "pipeline_lib" / "style.py")
style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(style)


def _song(bpm, length=200.0, offset=0.21, jitter=0.0):
    ibi = 60.0 / bpm
    return [offset + i * ibi + (jitter * ((-1) ** i)) for i in range(int((length - offset) / ibi))]


def _on_grid(t, grid, tol=0.02):
    return min(abs(t - g) for g in grid) <= tol


def check(bpm, dlg_len, punch_back, jitter=0.0):
    beats = _song(bpm, jitter=jitter)
    punch_rel = max(0.3, dlg_len - punch_back)
    r = style.plan_timeline(beats, song_drop=45.0, song_len=200.0, dlg_len=dlg_len, punch_rel=punch_rel)
    total, intro = r["total_s"], r["intro_s"]
    assert style.TIMELINE_MIN_S <= total <= style.TIMELINE_MAX_S, (bpm, dlg_len, total)
    assert style.INTRO_MIN_S - 1e-6 <= intro <= style.INTRO_MAX_S + 1.0, (bpm, intro)
    assert abs(r["dialogue_end_s"] - (intro + dlg_len)) < 1e-2
    assert abs(r["drop_s"] - (intro + punch_rel)) < 1e-2
    ic, oc = r["intro_cuts"], r["outro_cuts"]
    assert abs(sum(c for c, _ in ic) - intro) < 0.02, (bpm, dlg_len)
    assert abs(sum(c for c, _ in oc) - (total - r["dialogue_end_s"])) < 0.02, (bpm, dlg_len)
    assert len(ic) >= 4 and len(oc) >= 8, (bpm, dlg_len, len(ic), len(oc))
    for c, _ in ic + oc:
        assert style.MIN_CUT_S - 1e-6 <= c <= 4.0, (bpm, dlg_len, c)
    # song: starts >= 0, long enough, its drop beat lands on the punch word
    S = r["song_start"]
    assert S >= -1e-6 and S + total <= 200.0
    assert abs(r["song_drop_beat"] - S - r["drop_s"]) < 3e-3
    assert r["song_drop_beat"] >= 45.0 - 1e-3
    grid = [b - S for b in style.subdivide_slow(beats)]
    if not jitter:
        assert _on_grid(0.0, grid), (bpm, dlg_len)              # video starts on a beat
        assert _on_grid(r["drop_s"], grid)                     # drop on a beat
        t = 0.0
        for c, _ in ic[:-1]:                                   # every intro cut on the beat
            t += c
            assert _on_grid(t, grid), (bpm, dlg_len, t)
        t = r["dialogue_end_s"] + oc[0][0]
        for c, _ in oc[1:-1]:                                  # outro cuts on the beat after the first
            t += c
            assert _on_grid(t, grid), (bpm, dlg_len, t)
    # dialogue is the middle part: intro before it, a fast montage after it
    assert r["dialogue_start_s"] > 0 and total - r["dialogue_end_s"] >= style.OUTRO_MIN_S * 0.6
    return r


def test_grid_bpms_and_dialogue_lengths():
    for bpm, dlg, back in itertools.product([70, 85, 95, 110, 128, 140, 150, 160, 175],
                                            [6.0, 8.0, 11.0, 14.0, 18.0, 22.0], [0.4, 0.9]):
        check(bpm, dlg, back)


def test_jittery_beats():
    for bpm in (90, 128, 170):
        check(bpm, 12.0, 0.6, jitter=0.03)


def test_reference_like():
    r = check(128, 24.0, 0.7)   # reference: ~12s intro, ~24-29s dialogue, ~10s outro
    assert r["total_s"] <= 59.0


def test_song_shorter_than_video_raises():
    beats = _song(120, length=40.0)
    try:
        style.plan_timeline(beats, song_drop=30.0, song_len=40.0, dlg_len=10.0, punch_rel=9.5)
    except ValueError:
        pass
    else:
        raise AssertionError("song too short must raise ValueError")


def test_late_detected_drop_falls_back_to_earlier_beat():
    beats = _song(128, length=90.0)
    r = style.plan_timeline(beats, song_drop=85.0, song_len=90.0, dlg_len=12.0, punch_rel=11.4)
    assert r["song_start"] >= 0 and r["song_start"] + r["total_s"] <= 90.0


def test_half_time_song_is_subdivided():
    r = check(61, 10.0, 0.5)          # librosa half-time lock -> cuts must still be < ~1.1 s mostly
    cuts = [c for c, _ in r["outro_cuts"][1:-1]]
    assert r["ibi"] < 0.75 and sum(c <= 1.1 for c in cuts) >= 0.6 * len(cuts)


def test_fast_song_uses_two_beat_units():
    r = check(175, 10.0, 0.5)
    assert r["unit"] == 2
    assert all(c >= 0.6 for c, _ in r["outro_cuts"][1:-1])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
