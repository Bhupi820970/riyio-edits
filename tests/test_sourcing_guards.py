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


def test_catalog_60_per_mood_no_duplicates():
    import collections
    import re
    cnt = collections.Counter(s["mood"] for s in CAT)
    assert all(cnt[m] >= 60 for m in ("hype", "romance", "aggressive", "emotional", "epic", "dark")), cnt
    files = [s["file"] for s in CAT]
    assert len(files) == len(set(files))
    norm = lambda s: (re.sub(r"[^a-z0-9]", "", s["title"].lower()), re.sub(r"[^a-z0-9]", "", s["artist"].lower())[:8])
    keys = [norm(s) for s in CAT]
    assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]


def test_songs_do_not_repeat_until_mood_used_up():
    have = [s for s in CAT if s["mood"] == "hype"]
    used = []
    for i in range(len(have)):
        pick = SM.rank_songs("hype", have, {}, random.Random(i), recent=used)[0]
        assert pick not in used, (i, pick)
        used.append(pick)
    assert len(set(used)) == len(have)
    nxt = SM.rank_songs("hype", have, {}, random.Random(99), recent=used)[0]
    assert nxt == used[0]                       # then the least-recently-used one comes back first


def test_mark_used_roundtrip(tmp=Path("/tmp/riyio_used_songs_test.json")):
    tmp.unlink(missing_ok=True)
    SM.mark_used("hype_1.mp3", tmp)
    SM.mark_used("hype_2.mp3", tmp)
    assert SM.mark_used("hype_1.mp3", tmp) == ["hype_2.mp3", "hype_1.mp3"]
    tmp.unlink()


def test_sync_only_takes_originals():
    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_songs_bank as SY
    ok = {"title": "Ed Sheeran - Perfect (Official Music Video)", "channel": "Ed Sheeran", "duration": 263}
    topic = {"title": "Perfect", "channel": "Ed Sheeran - Topic", "duration": 263}
    for bad_t in ("Perfect - Ed Sheeran (Tribute)", "Perfect Ed Sheeran slowed + reverb", "Perfect (cover) Ed Sheeran",
                  "Perfect Ed Sheeran nightcore", "Perfect Ed Sheeran bass boosted"):
        assert SY._score({"title": bad_t, "channel": "Some Fan", "duration": 200}, "Perfect", "Ed Sheeran") < 4, bad_t
    assert SY._score(ok, "Perfect", "Ed Sheeran") >= 4 and SY._score(topic, "Perfect", "Ed Sheeran") >= 4
    assert SY._score({"title": "Perfect lyrics", "channel": "Lyric Vibes", "duration": 200}, "Perfect", "Ed Sheeran") < 4


def test_danza_kuduro_original_and_alternates():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    import sync_songs_bank as SY
    cat = json.loads((root / "config" / "songs_catalog.json").read_text())["songs"]
    r10 = next(s for s in cat if s["file"] == "romance_10.mp3")
    assert r10["title"] == "Danza Kuduro" and "slowed" not in r10["title"].lower() and "Lucenzo" in r10["artist"]
    vevo = {"title": "Don Omar - Danza Kuduro ft. Lucenzo", "channel": "DonOmarVEVO", "duration": 199}
    assert SY._score(vevo, r10["title"], r10["artist"]) >= 4
    assert SY._score({"title": "Danza Kuduro (Slowed + Reverb)", "channel": "x", "duration": 220},
                     r10["title"], r10["artist"]) < 4
    assert "romance_10.mp3" in json.loads((root / "config" / "songs_refetch.json").read_text())["files"]
    alts = json.loads((root / "config" / "songs_alternates.json").read_text())
    titles = {s["title"].lower() for s in cat}
    for mood in ("dark", "epic"):
        assert len(alts[mood]) >= 25
        for line in alts[mood]:
            t, a = line.split("|", 1)
            assert t.lower() not in titles and a.strip()
            assert not any(b in line.lower() for b in ("slowed", "sped up", "remix", "cover", "nightcore"))
    used = set(titles)
    first = SY.next_alternate("dark", alts, used)
    assert first and first[0].lower() in used and SY.next_alternate("dark", alts, used) != first


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
