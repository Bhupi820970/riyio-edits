"""BiBi Nov 24: no opening question caption ("WHAT DO YOU THINK..?") and a small glass-like RIYIO watermark."""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("style", ROOT / "pipeline_lib" / "style.py")
style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(style)

TSX = (ROOT / "remotion" / "src" / "JuraijEdit.tsx").read_text()
ROOT_TSX = (ROOT / "remotion" / "src" / "Root.tsx").read_text()
RUN = (ROOT / "run_v2.py").read_text()
GEM = (ROOT / "pipeline_lib" / "gemini_brain.py").read_text()


def test_plan_question_stripped():
    plan = {"hook_title": "Fear Is Earned", "hook_question": "WHAT DO YOU THINK..?", "question": "x?",
            "intro_caption": "y", "scene": "s"}
    style.strip_intro_question(plan)
    assert "hook_question" not in plan and "question" not in plan and "intro_caption" not in plan
    assert plan["hook_title"] == "Fear Is Earned" and plan["scene"] == "s"


def test_remotion_has_no_intro_question_slot():
    for src in (TSX, ROOT_TSX):
        assert "hookQuestion" not in src and "showHQ" not in src
    # captions render only inside the dialogue window
    assert "const cap = inDialogue ?" in TSX


def test_pipeline_and_prompt_never_ask_for_a_question():
    assert "hook_question" not in GEM.split("Rules:")[0]          # not in the director JSON schema
    assert not re.search(r"WHAT WOULD YOU DO|WHAT DO YOU THINK", RUN)
    assert '"hookQuestion"' not in RUN
    assert "strip_intro_question(plan)" in RUN


def test_watermark_small_and_glass():
    assert style.WM_FRAC <= 0.07 / 2 + 1e-9                         # about half the old 7% width
    assert 0.25 <= style.WM_OPACITY <= 0.35
    assert "wmOpacity" in TSX and "rgba(255,255,255,0.65)" not in TSX
    assert "style.WM_FRAC" in RUN and "style.WM_OPACITY" in RUN


def test_rgb_split_only_on_hits_and_light():
    assert style.RGB_SPLIT in style.frame_filter(True) and "rgbashift" not in style.frame_filter(False)
    assert "rgb=bool(pk.get(\"hit\"))" in RUN
    shift = max(abs(int(x)) for x in re.findall(r"[rb][hv]=(-?\d+)", style.RGB_SPLIT))
    assert shift <= 4


def test_hit_sfx_frames_wired():
    assert "hitFrames" in TSX and "whooshFrames" in TSX
    assert '"hitFrames": hit_frames' in RUN


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
