"""4K 4:5 HDR grade + optional Buffer post."""
from __future__ import annotations
import subprocess
from pathlib import Path

# Grade + sharpen are applied per clip before Remotion (pipeline_lib/style.py); here only a clean 4K upscale.
GRADE = "scale=2160:2700:flags=lanczos,unsharp=3:3:0.4:3:3:0.0"

# 60 fps output smoothing (idea 4): motion-compensated interpolation at 1080x1350 before the 4K upscale.
# scd = scene-change detection, so hard beat cuts stay hard cuts (no ghost blend between two shots).
SMOOTH60 = "minterpolate=fps=60:mi_mode=mci:mc_mode=obmc:me_mode=bidir:vsbmc=1:scd=fdiff:scd_threshold=8"
SMOOTH_TIMEOUT_S = 1800


def smooth60(src: Path, out: Path, timeout: int = SMOOTH_TIMEOUT_S) -> Path:
    """30 -> 60 fps. Falls back to plain frame doubling if interpolation is too slow / fails (never blocks a run)."""
    for vf, to in ((SMOOTH60, timeout), ("fps=60", 900)):
        cmd = ["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "14",
               "-pix_fmt", "yuv420p", "-c:a", "copy", str(out)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=to)
            if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
                print("SMOOTH60 ok:", vf.split("=")[0], flush=True)
                return out
            print("SMOOTH60 failed:", vf.split("=")[0], (r.stderr or "")[-300:], flush=True)
        except subprocess.TimeoutExpired:
            print(f"SMOOTH60 {vf.split('=')[0]} timed out after {to}s", flush=True)
    return src


def upscale_hdr(src: Path, out: Path, preset: str = "slow", fps60: bool = True):
    if fps60:
        src = smooth60(src, Path(str(out) + ".60fps.mp4"))
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", GRADE,
        "-c:v", "libx264", "-crf", "16", "-preset", preset, "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])

def buffer_post(video_url: str, caption: str, demo: bool):
    # media-cache upload + Buffer/YouTube posting is done by riyio-v2.yml after out.final.mp4 exists.
    print("Buffer publish deferred to workflow (media-cache + Buffer); demo=", demo)
