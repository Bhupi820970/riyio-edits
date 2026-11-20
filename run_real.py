#!/usr/bin/env python3
"""Real end-to-end runner for the RIYIO pipeline.

sourcing (yt-dlp + YT_COOKIES + Groq vet) -> Whisper transcript
-> vicestyle.py 4K dual render -> qc -> meta
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pipeline_lib.queue_manager import next_ready, mark_done, ensure_queue
from pipeline_lib.meta import generate_metadata
from pipeline_lib.qc import qc_video
from pipeline_lib.sourcing import ytdlp_cookie_args, search_queries_for, vet_keyframes_with_groq


def _run(cmd, timeout=300):
    print("+", " ".join(cmd[:8]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print((r.stderr or "")[-600:])
    return r


def download_clip(query: str, out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_dir / "clip.%(ext)s")
    cmd = ["yt-dlp", "--no-playlist", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
           "-o", tmpl, f"ytsearch1:{query}"]
    cmd += ytdlp_cookie_args()
    r = _run(cmd, timeout=180)
    for p in out_dir.glob("clip.*"):
        if p.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            return p
    return None


def transcribe(path: Path) -> str:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path), beam_size=1)
        return " ".join(s.text.strip() for s in segments)[:800]
    except Exception as e:
        print("whisper skip:", e)
        return ""


def main():
    ensure_queue()
    item = next_ready() or {"id": "demo", "topic": "cinematic dialogue scene", "genre": "movies"}
    print("ITEM", item.get("id"), item.get("topic"))

    clips = Path("clips")
    song = Path("song.mp3")
    # minimal silent song if none
    if not song.exists():
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=40",
              "-c:a", "libmp3lame", str(song)])

    queries = search_queries_for(item.get("genre", "movies"), item.get("topic", "cinematic scene"))
    clip = None
    for q in queries[:2]:
        clip = download_clip(q, clips)
        if clip:
            break
    if not clip:
        print("no clip downloaded — creating placeholder vertical source")
        clips.mkdir(exist_ok=True)
        clip = clips / "placeholder.mp4"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x111111:s=1920x1080:d=12",
              "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)])

    transcript = transcribe(clip)
    print("TRANSCRIPT:", transcript[:200] or "(none)")

    out = Path("out.mp4")
    cmd = [sys.executable, "vicestyle.py", "auto",
           "--song", str(song), "--clips", str(clips),
           "--out", str(out), "--mode", "dual", "--res", "1920x1080"]
    r = _run(cmd, timeout=600)
    shorts = Path("out.shorts.mp4")
    wide = Path("out.wide.mp4")
    if not shorts.exists() and wide.exists():
        # force a 9:16 from wide if engine didn't emit shorts
        _run(["ffmpeg", "-y", "-i", str(wide),
              "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
              "-c:v", "libx264", "-crf", "18", "-c:a", "copy", str(shorts)])

    meta = generate_metadata(item.get("topic", ""), item.get("genre", "movies"), transcript)
    print("META", json.dumps(meta, indent=2))
    Path("meta.json").write_text(json.dumps(meta, indent=2))

    if shorts.exists():
        ok, reasons = qc_video(shorts)
        print("QC", ok, reasons)
    if item.get("id") != "demo":
        mark_done(item["id"])
    print("DONE")


if __name__ == "__main__":
    main()
