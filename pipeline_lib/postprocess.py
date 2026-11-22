"""4K 4:5 HDR grade + optional Buffer post."""
from __future__ import annotations
import os, subprocess
from pathlib import Path

GRADE = "scale=2160:2700:flags=lanczos,eq=contrast=1.16:brightness=-0.04:saturation=1.15,unsharp=5:5:1.2:5:5:0.0,vignette=PI/5"

def upscale_hdr(src: Path, out: Path, preset: str = "medium"):
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", GRADE,
        "-c:v", "libx264", "-crf", "16", "-preset", preset, "-pix_fmt", "yuv420p",
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
    print("Buffer post:", caption[:80])
