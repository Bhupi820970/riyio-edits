"""riyio-v2: Gemini Vision + FFmpeg Juraij-style edit. demo_only aware."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

from pipeline_lib.gemini_brain import analyze, available as gemini_ok
from pipeline_lib.audio_sync import detect_beats, whisper_words

def run(cmd):
    print("+", " ".join(str(c) for c in cmd[:8]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-800:])
    return r

def main():
    demo = os.environ.get("DEMO_ONLY", "false").lower() in ("1", "true", "yes")
    print("DEMO_ONLY", demo, "| Gemini", gemini_ok())
    # placeholder: in full version this downloads via RapidAPI + songs-bank
    # For now expect clips/ and song.mp3 to exist, or exit with clear message
    clips = list(Path("clips").glob("*.mp4")) if Path("clips").exists() else []
    song = Path("song.mp3")
    if not clips or not song.exists():
        print("NO CLIPS OR SONG — full sourcing not wired yet in this stub")
        Path("out.shorts.mp4").write_bytes(b"")  # empty so workflow doesn't hard-fail on missing file
        print("STUB DONE")
        return
    src = clips[0]
    # 360p for Gemini
    prev = Path("preview360.mp4")
    run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=-2:360", "-c:v", "libx264", "-crf", "28", "-an", str(prev)])
    if gemini_ok():
        plan = analyze(prev)
        print("GEMINI PLAN", json.dumps(plan)[:400])
        if plan.get("reject"):
            raise SystemExit("Gemini rejected video: " + plan.get("reject_reason", ""))
    else:
        plan = {"dialogue_start": 5.0, "dialogue_end": 20.0, "action_cuts": [25, 30, 35, 40, 45], "hook": "She read him cold"}
    Path("plan.json").write_text(json.dumps(plan, indent=2))
    # Cut dialogue
    ds, de = float(plan["dialogue_start"]), float(plan["dialogue_end"])
    dlg = Path("dialogue.mp4")
    run(["ffmpeg", "-y", "-ss", str(ds), "-to", str(de), "-i", str(src), "-c", "copy", str(dlg)])
    words = whisper_words(dlg)
    Path("words.json").write_text(json.dumps(words))
    print("WORDS", len(words))
    # Simple output: dialogue + title overlay (full version does beat-drop montage)
    hook = plan.get("hook", "Money Really Talks")
    out = Path("out.shorts.mp4")
    vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,drawbox=x=0:y=0:w=1080:h=120:color=white@0.9:t=fill,drawtext=text='\"{hook}\"':fontcolor=black:fontsize=40:x=(w-text_w)/2:y=35"
    run(["ffmpeg", "-y", "-i", str(dlg), "-vf", vf, "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(out)])
    print("DONE", out, out.stat().st_size)
    if demo:
        print("DEMO_ONLY — skipping Buffer")

if __name__ == "__main__":
    main()
