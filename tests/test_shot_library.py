"""Shot library per title (idea 5): save good shots, reuse known-good sources, caps, exclusions."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("montage_select", ROOT / "pipeline_lib" / "montage_select.py")
M = importlib.util.module_from_spec(_spec)
sys.modules["montage_select"] = M
_spec.loader.exec_module(M)
from pipeline_lib import shot_library as SL  # noqa: E402


def _chunks(n, energy=6.0):
    return [M.Chunk("main", 10.0 + i * 4, 12.0 + i * 4, 1000 + i, motion=12.0, energy=energy, kind="action", loud=5.0)
            for i in range(n)]


def test_key_normalises_title():
    assert SL.key("Meet the Parents (2000)") == SL.key("meet the  parents") == "meet the parents"


def test_add_and_reuse():
    lib = {}
    n = SL.add(lib, "Heat (1995)", "abc123", {"url": "https://youtu.be/abc123", "title": "Heat clip"}, _chunks(5), now=1)
    assert n == 5
    src = SL.sources_for(lib, "heat")
    assert src and src[0]["id"] == "abc123" and src[0]["url"].endswith("abc123")
    shot = src[0]["shots"][0]
    assert {"s", "e", "energy", "kind", "hash", "loud", "motion"} <= set(shot)
    g = SL.as_gemini_shots(src[0]["shots"])
    assert all(x["s"] <= y["t"] <= x["e"] for x, y in zip(src[0]["shots"], g))


def test_weak_shots_not_saved_and_caps():
    lib = {}
    assert SL.add(lib, "Heat", "weak", {"url": "u"}, [M.Chunk("main", 1, 2, 1, motion=1.0, energy=0.0)]) == 0
    assert SL.add(lib, "Heat", "big", {"url": "u2"}, _chunks(80)) == SL.MAX_SHOTS
    for i in range(SL.MAX_SOURCES + 3):
        SL.add(lib, "Heat", f"v{i}", {"url": f"https://youtu.be/v{i}"}, _chunks(3), now=100 + i)
    assert len(lib["heat"]["sources"]) == SL.MAX_SOURCES


def test_exclusions_main_and_used():
    lib = {}
    SL.add(lib, "Heat", "main1", {"url": "https://youtu.be/main1"}, _chunks(3))
    SL.add(lib, "Heat", "x2", {"url": "https://youtu.be/x2"}, _chunks(3))
    got = SL.sources_for(lib, "Heat", exclude_ids={"main1"}, exclude_urls={"https://youtu.be/x2"})
    assert got == []
    assert [s["id"] for s in SL.sources_for(lib, "Heat", exclude_ids={"main1"})] == ["x2"]


def test_library_shots_still_no_repeats():
    """Reused library shots go through the same select/audit: no repeats per video."""
    lib = {}
    SL.add(lib, "Heat", "x1", {"url": "u"}, _chunks(40))
    chunks = [M.Chunk("x1", 10.0 + i * 4, 12.0 + i * 4, (i * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF, motion=10.0,
                      shot=i) for i in range(40)]
    M.apply_gemini(chunks, SL.as_gemini_shots(SL.sources_for(lib, "Heat")[0]["shots"]), "x1")
    assert sum(c.energy > 0 for c in chunks) >= 30
    picks = M.select(chunks, [0.9] * 6, [0.47] * 14)
    assert M.audit(picks) == []


def test_save_roundtrip(tmp=Path("/tmp/riyio_shotlib_test.json")):
    lib = {}
    SL.add(lib, "Heat", "a", {"url": "u"}, _chunks(2))
    SL.save(lib, tmp)
    assert SL.load(tmp)["heat"]["sources"]["a"]["shots"]
    tmp.unlink()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
