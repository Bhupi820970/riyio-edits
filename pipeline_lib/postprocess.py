"""4K 4:5 HDR grade + optional Buffer post."""
from __future__ import annotations
import subprocess
from pathlib import Path

# Grade + sharpen are applied per clip before Remotion (pipeline_lib/style.py); here only a clean 4K upscale.
GRADE = "scale=2160:2700:flags=lanczos,unsharp=3:3:0.4:3:3:0.0"

def upscale_hdr(src: Path, out: Path, preset: str = "slow"):
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
