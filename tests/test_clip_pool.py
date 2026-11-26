import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline_lib import clip_pool as P  # noqa: E402


def _doc(ready, used=0, refilling=False):
    clips = [{"id": f"r{i:010d}", "url": f"https://www.youtube.com/watch?v=r{i:010d}", "state": "ready"} for i in range(ready)]
    clips += [{"id": f"u{i:010d}", "url": "x", "state": "used"} for i in range(used)]
    return {"refilling": refilling, "clips": clips}


def test_refill_starts_at_50_or_below_and_stops_at_100():
    assert P.refill_plan(_doc(50)) == (True, 50)
    assert P.refill_plan(_doc(51)) == (False, 0)
    assert P.refill_plan(_doc(70, refilling=True)) == (True, 30)       # keeps going until ~100
    assert P.refill_plan(_doc(100, refilling=True)) == (False, 0)
    assert P.refill_plan(_doc(10, used=200))[1] == 90                  # used clips never count


def test_pool_clip_is_used_once():
    d = _doc(2)
    url = d["clips"][0]["url"]
    assert P.by_url(d, url)["state"] == "ready"
    assert P.set_state(d, url, "used")
    assert len(P.usable(d)) == 1 and url not in [c["url"] for c in P.usable(d)]
    assert not P.set_state(d, "https://www.youtube.com/watch?v=zzzzzzzzzzz", "used")


def test_balanced_order_round_robins_genres():
    es = [{"genre": "movies", "i": i} for i in range(3)] + [{"genre": "anime", "i": i} for i in range(2)]
    order = [e["genre"] for e in P.balanced_order(es, ["movies", "anime"])]
    assert order[:4] == ["movies", "anime", "movies", "anime"]


def test_genres_are_parsed_not_imported():
    sys.path.insert(0, str(ROOT / "scripts"))
    import clip_pool as CP
    g = CP.genres()
    assert {"movies", "anime", "games", "web_series", "cartoons"} <= set(g)
