"""Caption size rules: readable, never huge, sized by word count and space beside the speaker."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline_lib import captions as C  # noqa: E402
import caption_patterns as CP  # noqa: E402


def test_sizes_clamped_to_reference_range():
    for pat in CP.PATTERNS:
        items, _ = C.style_items([{"word": "you", "s": 0, "e": .2, "i": 0}, {"word": "courage", "s": .2, "e": .6, "i": 1},
                                  {"word": "remarkable", "s": .6, "e": 1, "i": 2}], pat, 1080 * C.BASE_FRAC * 1.22, 0, 1)
        for it in items:
            lo, hi = C.SIZE_LIMITS["punch" if it.get("punch") else ("filler" if it["small"] else "key")]
            assert lo <= it["size"] <= hi, (pat["id"], it)
        assert max(it["size"] for it in items) <= 112   # old demo had 151-170 px words


def test_fewer_words_bigger():
    assert C.WORDS_SCALE[1] > C.WORDS_SCALE[2] > C.WORDS_SCALE[3]


def test_free_width_beside_speaker():
    pat = CP.PATTERNS[0]
    left_face = (0.05, 0.3, 0.30, 0.6)     # face on the left -> lots of room on the right
    centre_face = (0.40, 0.3, 0.60, 0.6)
    assert C.free_width(left_face, pat, 1080) >= C.free_width(centre_face, pat, 1080)
    assert 1080 * 0.38 <= C.free_width(centre_face, pat, 1080) <= 1080 * 0.62
    assert C.free_width(None, pat, 1080) == 1080 * 0.62


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
