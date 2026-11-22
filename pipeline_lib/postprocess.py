"""4K HDR grade + optional Buffer post."""
from __future__ import annotations
import os, subprocess
from pathlib import Path

GRADE = "scale=2160:3840:flags=lanczos,eq=contrast=1.14:brightness=-0.03:saturation=1.12,unsharp=5:5:1.15:5:5:0.0,vignette=PI/5"

def upscale_hdr(src: Path, out: Path):
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", GRADE,
        "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])

def buffer_post(video_url: str, caption: str, demo: bool):
    if demo or not os.environ.get("BUFFER_ACCESS_TOKEN"):
        print("skip Buffer (demo or no token)")
        return
    # real Buffer GraphQL call would go here
    print("Buffer post stub:", caption[:80])
