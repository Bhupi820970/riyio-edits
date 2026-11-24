"""Exposure guard (BiBi Nov 24 'jyada hi dark'): the grade keeps the source brightness (<= 8% darker, aim ~5%)."""
import importlib.util
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("style", ROOT / "pipeline_lib" / "style.py")
style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(style)
RUN = (ROOT / "run_v2.py").read_text()

OLD_GRADE = ("eq=contrast=1.25:saturation=0.62:brightness=-0.035:gamma=0.95,"
             "colorbalance=rs=-0.05:gs=0.0:bs=0.08:rh=0.02:bh=-0.02,"
             "curves=master='0/0 0.08/0.02 0.5/0.48 1/1',unsharp=5:5:1.0:5:5:0.0,noise=alls=7:allf=t")
# synthetic "scenes": testsrc2 pattern pulled down to a dark night scene, a dim interior and a normal day shot
# (full-range frames like the JPEG source screens, darkened in RGB like a real low-key scene)
# testsrc2 is far more saturated than film, so it is toned down to film-like colour first (hue=s=0.35)
SCENES = {"night": "hue=s=0.35,format=rgb24,colorlevels=romax=0.3:gomax=0.3:bomax=0.3",
          "dim": "hue=s=0.35,format=rgb24,colorlevels=romax=0.55:gomax=0.55:bomax=0.55", "day": "hue=s=0.35"}


def _mean(vf, scene):
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=0.2", "-frames:v", "1",
                        "-vf", f"format=yuvj420p,{SCENES[scene]},{vf},format=yuvj420p,scale=64:36,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    return sum(r.stdout) / len(r.stdout)


def _dark_share(vf, scene):
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=0.2", "-frames:v", "1",
                        "-vf", f"format=yuvj420p,{SCENES[scene]},{vf},format=yuvj420p,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True)
    return sum(1 for b in r.stdout if b < 16) / len(r.stdout)


def test_luma_drop_pure():
    assert abs(style.luma_drop([90, 45], [100, 50]) - 0.1) < 1e-9
    assert style.luma_drop([110], [100]) < 0
    assert style.luma_drop([], []) == 0.0 and style.luma_drop([5], [0]) == 0.0
    assert style.LUMA_MAX_DROP <= 0.08


def test_grade_has_no_darkening_filters():
    g = style.GRADE
    assert "contrast=" not in g and "gamma=" not in g and "brightness=-" not in g and "vignette" not in g
    assert "0.08/0.02" not in g                       # the old black crush
    assert style.FILL_BRIGHTNESS >= -0.06


def test_grade_keeps_exposure_dark_and_bright_scenes():
    if not shutil.which("ffmpeg"):
        print("skip: no ffmpeg")
        return
    for scene in SCENES:
        src, new = _mean("null", scene), _mean(style.GRADE, scene)
        assert abs(new / src - 1) <= 0.05, (scene, src, new)                 # within ~5% of the source
        assert _dark_share(style.GRADE, scene) <= _dark_share("null", scene) + 0.03, scene   # no crushed blacks


def test_old_grade_would_fail_the_guard():
    if not shutil.which("ffmpeg"):
        return
    drop = style.luma_drop([_mean(OLD_GRADE, s) for s in ("night", "dim")], [_mean("null", s) for s in ("night", "dim")])
    assert drop > style.LUMA_MAX_DROP, drop


def test_pipeline_qc_uses_the_guard():
    assert "exposure_check(draft, samples, pic)" in RUN
    assert "style.LUMA_MAX_DROP" in RUN and "darker than the source" in RUN


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
