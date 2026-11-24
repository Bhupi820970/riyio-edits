"""Song by mood + tempo (idea 3): never an emotional song on a comedy scene; tempo-matched songs first."""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline_lib import song_mood as SM  # noqa: E402

CAT = SM.load_catalog(ROOT / "config" / "songs_catalog.json")
MOOD = {s["file"]: s["mood"] for s in CAT}


def test_catalog_loaded_with_moods():
    assert len(CAT) >= 50 and {"emotional", "hype", "dark", "epic"} <= set(MOOD.values())


def test_no_emotional_song_on_comedy_hype_dark():
    for scene in ("comedy", "hype", "dark"):
        for seed in range(5):
            files = SM.rank_songs(scene, CAT, {}, random.Random(seed))
            assert files, scene
            assert not any(MOOD[f] in ("emotional", "romance") for f in files), scene


def test_emotional_scene_gets_emotional_first():
    files = SM.rank_songs("emotional", CAT, {}, random.Random(1))
    assert MOOD[files[0]] == "emotional"
    assert not any(MOOD[f] in ("hype", "aggressive") for f in files)


def test_tempo_ranking_and_far_off_tempo_dropped():
    tags = {f: {"bpm": 150} for f in MOOD if MOOD[f] == "hype"}
    slow = [f for f in MOOD if MOOD[f] == "hype"][:3]
    for f in slow:
        tags[f] = {"bpm": 72}                     # 72 BPM ballad-like track: 43 BPM below the hype range
    files = SM.rank_songs("hype", CAT, tags, random.Random(2))
    assert not any(f in files for f in slow)
    assert SM.tempo_fit(150, "hype") == 0 and SM.tempo_fit(90, "hype") > 0


def test_fold_bpm_half_double_time():
    assert SM.fold_bpm(64) == 128 and SM.fold_bpm(300) == 150 and SM.fold_bpm(0) == 0


def test_scene_mood_normalised():
    assert SM.scene_mood({"scene_mood": "Comedy"}) == "comedy"
    assert SM.scene_mood({"mood": "emotional_romance"}) == "emotional"
    assert SM.scene_mood({"mood": "epic_cinematic"}) == "epic"
    assert SM.scene_mood({"scene_mood": "funny"}) == "comedy"
    assert SM.scene_mood({}) == "dark"


def test_tags_cache_roundtrip(tmp=Path("/tmp/riyio_song_tags_test.json")):
    t = {"hype_1.mp3": SM.tag_entry("hype", 64.0, 0.12345, 30.0)}
    SM.save_tags(t, tmp)
    back = SM.load_tags(tmp)
    assert back["hype_1.mp3"]["bpm"] == 128 and back["hype_1.mp3"]["mood"] == "hype"
    tmp.unlink()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
