"""No source clip goes into two riyio videos: clip ledger (pipeline_lib/clip_reserve.py), no network.

Reserved the moment a run picks it (main clip + montage extras), used for good once the video renders,
released on failure, stale reservations expire after 8 h, unreachable ledger -> clip skipped."""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline_lib import clip_reserve as CR  # noqa: E402
from pipeline_lib import clip_pool as P  # noqa: E402

A = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
B = "https://youtu.be/bbbbbbbbbbb"


def _be():
    """Fresh local ledger file (no network); runs under pytest and plain `python tests/...`."""
    return CR.LocalBackend(Path(tempfile.mkdtemp()) / "clip_reservations.json")


def _r(owner, be):
    return CR.Reservations(owner, backend=be, log=lambda *a: None, tries=2, video=owner)


def test_keys_are_youtube_ids():
    assert CR.base_id(A + "&t=30") == "yt:aaaaaaaaaaa"
    assert CR.base_id("https://www.youtube.com/shorts/aaaaaaaaaaa") == "yt:aaaaaaaaaaa"
    assert CR.base_id("aaaaaaaaaaa") == "yt:aaaaaaaaaaa"
    assert CR.base_id(B) == "yt:bbbbbbbbbbb"


def test_two_runs_cannot_hold_the_same_clip():
    be = _be()
    assert _r("1-1", be).reserve(A)
    assert not _r("2-1", be).reserve(A + "&t=5")


def test_rendered_video_uses_its_clips_forever():
    be = _be()
    r = _r("1-1", be)
    r.reserve(A)
    r.reserve(B)
    r.confirm([A], video="1-1")
    r.release()
    later = _r("9-1", be)
    assert not later.reserve(A)
    assert later.reserve(B)
    assert CR.ledger_used(be) == {"yt:aaaaaaaaaaa"}


def test_failed_render_releases():
    be = _be()
    r = _r("1-1", be)
    r.reserve(A)
    r.release()
    assert _r("2-1", be).reserve(A)


def test_stale_reservation_expires():
    be = _be()
    _r("1-1", be).reserve(A)
    doc, sha = be.read()
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=CR.RESERVE_TTL_H + 1)
    doc["clips"]["yt:aaaaaaaaaaa"]["at"] = old.isoformat(timespec="seconds")
    be.write(doc, sha, "age")
    assert _r("2-1", be).reserve(A)


def test_unreachable_ledger_skips_clip():
    class Down:
        def locked(self):
            raise OSError("down")

        def read(self):
            raise OSError("down")
    assert not _r("1-1", Down()).reserve(A)


def test_pool_treats_used_clips_as_gone():
    doc = {"clips": [{"id": "aaaaaaaaaaa", "url": A, "state": "ready"},
                     {"id": "bbbbbbbbbbb", "url": B, "state": "ready"}]}
    assert P.drop_used(doc, {"aaaaaaaaaaa"}) == 1
    assert [c["id"] for c in P.usable(doc)] == ["bbbbbbbbbbb"]
    assert P.refill_plan(doc)[1] == P.TARGET - 1


def test_run_v2_wires_the_ledger():
    src = (ROOT / "run_v2.py").read_text()
    assert "if not _claim(url):" in src                      # main clip reserved before download
    assert src.count("if not _claim(") >= 3                  # + both montage-extra paths
    assert "RES.confirm(_video_sources(ctx)" in src and "RES.release()" in src
    assert "RES.release([url])" in src                       # rejected candidate goes back


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
