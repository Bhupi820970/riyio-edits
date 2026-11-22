"""riyio-v2 Iteration 1: Gemini + sourcing stubs + Remotion props export."""
from __future__ import annotations
import json, os, subprocess
from pathlib import Path

from pipeline_lib.gemini_brain import analyze, available as gemini_ok
from pipeline_lib.audio_sync import detect_beats, whisper_words
from pipeline_lib.sourcing import pick_song, is_blacklisted

def run(cmd):
    print("+", " ".join(str(c) for c in cmd[:6]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[-600:])
    return r

def main():
    demo = os.environ.get("DEMO_ONLY", "false").lower() in ("1", "true", "yes")
    print("DEMO_ONLY", demo, "| Gemini", gemini_ok())
    # Expect pre-placed clips for now; full RapidAPI download in Iteration 2
    clips_dir = Path("clips")
    clips = list(clips_dir.glob("*.mp4")) if clips_dir.exists() else []
    song = Path("song.mp3")
    if not clips:
        print("NO CLIPS — sourcing download not fully wired yet")
        Path("remotion-props.json").write_text(json.dumps({"status": "no_clips"}))
        return
    src = clips[0]
    prev = Path("preview360.mp4")
    run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=-2:360", "-c:v", "libx264", "-crf", "28", "-an", str(prev)])
    plan = analyze(prev) if gemini_ok() else {
        "dialogue_start": 5, "dialogue_end": 22, "action_cuts": [25, 30, 35, 40, 45],
        "mood": "dark_hype", "hook": "She read him cold", "caption_y": "lower-center",
        "post_caption": "Clip: Unknown | Credit: Source | Edited under Fair Use."
    }
    if plan.get("reject"):
        raise SystemExit("Rejected: " + plan.get("reject_reason", ""))
    Path("plan.json").write_text(json.dumps(plan, indent=2))
    # cut dialogue
    ds, de = float(plan["dialogue_start"]), float(plan["dialogue_end"])
    dlg = Path("dialogue.mp4")
    run(["ffmpeg", "-y", "-ss", str(max(0, ds)), "-to", str(de), "-i", str(src), "-c", "copy", str(dlg)])
    words = whisper_words(dlg)
    beats = detect_beats(song) if song.exists() else {"drop": 10.0, "beats": []}
    props = {
        "hook": plan.get("hook", "She read him cold"),
        "dialogueSrc": str(dlg),
        "actionClips": [],  # filled in full version from action_cuts
        "words": words,
        "songSrc": str(song) if song.exists() else "",
        "beatDropFrame": int(beats.get("drop", 10) * 30),
        "post_caption": plan.get("post_caption", ""),
        "mood": plan.get("mood", "dark_hype"),
    }
    Path("remotion-props.json").write_text(json.dumps(props, indent=2))
    print("PROPS written", len(words), "words | drop frame", props["beatDropFrame"])
    # Basic FFmpeg fallback output so something is produced
    out = Path("out.shorts.mp4")
    hook = props["hook"]
    vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,drawbox=x=0:y=0:w=1080:h=130:color=white@0.92:t=fill,drawtext=text='\"{hook}\"':fontcolor=black:fontsize=40:x=(w-text_w)/2:y=40"
    run(["ffmpeg", "-y", "-i", str(dlg), "-vf", vf, "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(out)])
    print("FALLBACK OUT", out.stat().st_size)
    if demo:
        print("DEMO_ONLY skip Buffer")

if __name__ == "__main__":
    main()
