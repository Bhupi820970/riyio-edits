"""riyio-v2 full: RapidAPI -> Gemini -> cuts -> Remotion props -> FFmpeg fallback."""
from __future__ import annotations
import json, os, subprocess
from pathlib import Path

from pipeline_lib.gemini_brain import analyze, available as gemini_ok
from pipeline_lib.audio_sync import detect_beats, whisper_words
from pipeline_lib.sourcing import search_and_download, pick_or_download_song
from pipeline_lib.postprocess import upscale_hdr, buffer_post

def run(cmd):
    print("+", " ".join(str(c) for c in cmd[:7]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[-700:])
    return r

def main():
    demo = os.environ.get("DEMO_ONLY", "false").lower() in ("1", "true", "yes")
    query = os.environ.get("QUERY", "Game of Thrones iconic scene 4K no subtitles")
    print("DEMO", demo, "GEMINI", gemini_ok())

    Path("clips").mkdir(exist_ok=True)
    src = Path("clips/source.mp4")
    info = search_and_download(query, src)
    if not info:
        print("NO DOWNLOAD — check RAPIDAPI keys")
        return
    print("DOWNLOADED", info.get("title"), info.get("channel"))

    prev = Path("preview360.mp4")
    run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=-2:360", "-c:v", "libx264", "-crf", "28", "-an", str(prev)])

    plan = analyze(prev) if gemini_ok() else {
        "dialogue_start": 8, "dialogue_end": 24, "action_cuts": [30, 35, 40, 45, 50],
        "mood": "dark_hype", "hook": "She read him cold",
        "post_caption": f"Clip: {info.get('title','')} | Credit: {info.get('channel','')} | Edited under Fair Use.",
        "caption_y": "lower-center",
    }
    if plan.get("reject"):
        raise SystemExit("Rejected")
    Path("plan.json").write_text(json.dumps(plan, indent=2))

    # cut dialogue from original
    ds, de = float(plan["dialogue_start"]), float(plan["dialogue_end"])
    dlg = Path("clips/dialogue.mp4")
    run(["ffmpeg", "-y", "-ss", str(max(0, ds)), "-to", str(de), "-i", str(src), "-c", "copy", str(dlg)])

    # cut action clips
    action_paths = []
    for i, t in enumerate(plan.get("action_cuts", [])[:6]):
        ap = Path(f"clips/action_{i}.mp4")
        run(["ffmpeg", "-y", "-ss", str(max(0, float(t))), "-t", "0.8", "-i", str(src), "-c", "copy", str(ap)])
        action_paths.append(str(ap))

    words = whisper_words(dlg)
    song = pick_or_download_song(plan.get("mood", "dark_hype"), Path("songs"), Path("clips/song.mp3"))
    beats = detect_beats(song) if song and song.exists() else {"drop": 10.0}

    props = {
        "hook": plan.get("hook", "She read him cold"),
        "dialogueSrc": str(dlg.resolve()),
        "actionClips": [str(Path(p).resolve()) for p in action_paths],
        "words": words,
        "songSrc": str(song.resolve()) if song else "",
        "beatDropFrame": int(beats.get("drop", 10) * 30),
        "post_caption": plan.get("post_caption", ""),
    }
    Path("remotion-props.json").write_text(json.dumps(props, indent=2))
    print("PROPS", len(words), "words,", len(action_paths), "actions")

    # Copy assets into remotion/public/assets and use relative paths
    assets_dir = Path("remotion/public/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    # clear old
    for f in assets_dir.glob("*"):
        f.unlink(missing_ok=True)
    # copy dialogue + actions + song
    import shutil
    rel_dialogue = ""
    if dlg.exists():
        shutil.copy(dlg, assets_dir / "dialogue.mp4")
        rel_dialogue = "assets/dialogue.mp4"
    rel_actions = []
    for i, ap in enumerate(action_paths):
        srcp = Path(ap)
        if srcp.exists():
            dest = assets_dir / f"action_{i}.mp4"
            shutil.copy(srcp, dest)
            rel_actions.append(f"assets/action_{i}.mp4")
    rel_song = ""
    if song and song.exists():
        shutil.copy(song, assets_dir / "song.mp3")
        rel_song = "assets/song.mp3"
    # rebuild props with relative paths
    props["dialogueSrc"] = rel_dialogue
    props["actionClips"] = rel_actions
    props["songSrc"] = rel_song
    Path("remotion-props.json").write_text(json.dumps(props, indent=2))
    print("ASSETS ready", rel_dialogue, len(rel_actions), "actions")

    # Remotion render only (no FFmpeg fallback)
    remotion_out = Path("out_remotion.mp4")
    run(["bash", "-c", "cd remotion && npx @remotion/cli render src/index.ts JuraijEdit ../out_remotion.mp4 --props=../remotion-props.json"])
    if not remotion_out.exists() or remotion_out.stat().st_size < 1000:
        raise RuntimeError("Remotion produced no output")
    base = remotion_out

    final = Path("out.final.mp4")
    upscale_hdr(base, final)
    print("FINAL", final.stat().st_size)
    buffer_post("", props["post_caption"], demo)

if __name__ == "__main__":
    main()
