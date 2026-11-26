"""Guards for the Nov 26 failure: songs missing from songs-bank, too-long sources, sync script wiring."""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline_lib import song_mood as SM  # noqa: E402
from pipeline_lib import sourcing as S  # noqa: E402

CAT = SM.load_catalog(ROOT / "config" / "songs_catalog.json")
MOOD = {s["file"]: s["mood"] for s in CAT}
# what the songs-bank release really held on Nov 26 2026 (no hype / romance, aggressive 1-3 only)
BANK_NOV26 = ({f"dark_{i}.mp3" for i in range(1, 11)} | {f"epic_{i}.mp3" for i in range(1, 11)}
              | {f"emotional_{i}.mp3" for i in range(2, 11)} | {f"aggressive_{i}.mp3" for i in range(1, 4)})


def test_pool_only_has_songs_that_exist():
    have = SM.only_available(CAT, BANK_NOV26)
    for scene in SM.SCENE_MOODS:
        for seed in range(5):
            pool = SM.rank_songs(scene, have, {}, random.Random(seed))[:8]
            assert pool, scene                                  # every scene mood gets real songs
            assert all(f in BANK_NOV26 for f in pool), scene    # never a missing file


def test_comedy_still_never_emotional_and_hype_first_when_present():
    have = SM.only_available(CAT, BANK_NOV26)
    pool = SM.rank_songs("comedy", have, {}, random.Random(3))
    assert not any(MOOD[f] in ("emotional", "romance") for f in pool)
    assert MOOD[pool[0]] == "aggressive"                       # hype missing -> aggressive before epic
    full = SM.rank_songs("comedy", CAT, {}, random.Random(3))
    assert MOOD[full[0]] == "hype"


def test_listing_failed_keeps_catalog():
    assert SM.only_available(CAT, None) == CAT


def test_parse_duration():
    assert S.parse_duration(312) == 312 and S.parse_duration("312") == 312
    assert S.parse_duration("5:12") == 312 and S.parse_duration("1:02:03") == 3723
    assert S.parse_duration({"simpleText": "40:00"}) == 2400
    assert S.parse_duration("") == 0 and S.parse_duration(None) == 0 and S.parse_duration("live") == 0


def test_too_long_results_skipped_before_download():
    assert "too long" in S.skip_reason({"title": "God of War cutscene", "channel": "x", "duration": 40 * 60})
    assert S.skip_reason({"title": "God of War cutscene", "channel": "x", "duration": 300}) == ""
    assert S.skip_reason({"title": "God of War cutscene", "channel": "x", "duration": 0}) == ""


def test_sync_script_imports_resolve():
    for name in ("AllKeysExhausted", "RapidAPIError", "rapid_available", "rapid_download", "rapid_search"):
        assert hasattr(S, name), name
    assert issubclass(S.AllKeysExhausted, S.RapidAPIError)
    import inspect
    assert "max_minutes" in inspect.signature(S.rapid_download).parameters


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
