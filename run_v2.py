"""riyio-v2 full: RapidAPI -> Gemini -> cuts -> Remotion props -> FFmpeg fallback."""
from __future__ import annotations
import traceback

import json, sys, os, subprocess, shutil
from pathlib import Path

from pipeline_lib.gemini_brain import analyze, available as gemini_ok
from pipeline_lib.audio_sync import detect_beats, whisper_words
from pipeline_lib.sourcing import search_and_download, pick_or_download_song
from pipeline_lib.postprocess import upscale_hdr, buffer_post

def run(cmd):
    print("+", " ".join(str(c) for c in cmd[:7]), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        err = ((r.stderr or "") + "\n" + (r.stdout or ""))[-2000:]
        print(err, flush=True)
        raise RuntimeError(err)
    return r


def probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except Exception:
        return 60.0


def _num(val, default):
    if val is None or val == "":
        return float(default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(default)


def ffmpeg_cut(src, dest, start, duration, audio=True):
    """Re-encode (not stream-copy) so Chromium/Remotion can seek the clip."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.2f}", "-t", f"{duration:.2f}", "-i", str(src),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd.append(str(dest))
    run(cmd)
    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError(f"cut produced no file: {dest}")


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
    run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", str(prev)])

    plan = analyze(prev) if gemini_ok() else {
        "dialogue_start": 8, "dialogue_end": 24, "action_cuts": [30, 35, 40, 45, 50],
        "mood": "dark_hype", "hook": "She read him cold",
        "post_caption": f"Clip: {info.get('title','')} | Credit: {info.get('channel','')} | Edited under Fair Use.",
        "caption_y": "lower-center",
    }
    if plan.get("reject"):
        reason = plan.get("reject_reason") or "unspecified"
        if demo:
            print("GEMINI rejected clip, continuing with default window for demo:", reason, flush=True)
            plan.setdefault("dialogue_start", 8)
            plan.setdefault("dialogue_end", 24)
            plan.setdefault("action_cuts", [30, 35, 40, 45, 50])
            plan.setdefault("mood", "dark_hype")
            plan.setdefault("hook", "She read him cold")
            plan["reject"] = False
        else:
            raise SystemExit("Rejected: " + str(reason))
    Path("plan.json").write_text(json.dumps(plan, indent=2))

    # cut dialogue from original (sanitized, re-encoded)
    print("[3] FFmpeg cuts", flush=True)
    dur = probe_duration(src)
    print("source duration", dur, flush=True)
    ds = _num(plan.get("dialogue_start"), 8)
    de = _num(plan.get("dialogue_end"), 24)
    ds = max(0.0, min(ds, max(0.0, dur - 12)))
    if de <= ds + 3:
        de = min(dur, ds + 18)
    de = min(de, dur)
    if de <= ds + 0.8:
        raise RuntimeError(f"cannot cut dialogue: ds={ds} de={de} dur={dur}")
    dlg = Path("clips/dialogue.mp4")
    ffmpeg_cut(src, dlg, ds, de - ds, audio=True)

    # cut action clips (sanitized, re-encoded)
    action_paths = []
    for i, t in enumerate(plan.get("action_cuts", [])[:6]):
        try:
            start = float(t)
        except Exception:
            continue
        start = max(0.0, min(start, max(0.0, dur - 2)))
        clip_dur = 0.8
        if start + clip_dur > dur:
            start = max(0.0, dur - clip_dur)
        ap = Path(f"clips/action_{i}.mp4")
        ffmpeg_cut(src, ap, start, clip_dur, audio=False)
        action_paths.append(str(ap))

    words = whisper_words(dlg)
    song = pick_or_download_song(plan.get("mood", "dark_hype"), Path("songs"), Path("clips/song.mp3"))
    beats = detect_beats(song) if song and song.exists() else {"drop": 10.0}

    # Keep the beat drop inside the 30s / 900-frame composition
    drop_s = _num(beats.get("drop"), 10)
    drop_s = min(max(drop_s, 8.0), 24.0)

    props = {
        "hook": plan.get("hook", "She read him cold"),
        "dialogueSrc": str(dlg.resolve()),
        "actionClips": [str(Path(p).resolve()) for p in action_paths],
        "words": words,
        "songSrc": str(song.resolve()) if song else "",
        "beatDropFrame": int(drop_s * 30),
        "post_caption": plan.get("post_caption", ""),
    }
    Path("remotion-props.json").write_text(json.dumps(props, indent=2))
    print("[3] FFmpeg cuts done", flush=True)
    print("PROPS", len(words), "words,", len(action_paths), "actions, drop", props["beatDropFrame"], "song", bool(song))

    # Copy assets into remotion/public/assets and use relative paths
    assets_dir = Path("remotion/public/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    # clear old
    for f in assets_dir.glob("*"):
        f.unlink(missing_ok=True)
    # copy dialogue + actions + song
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
    print("ASSETS ready", rel_dialogue, len(rel_actions), "actions, song", rel_song or "NONE", flush=True)

    # Remotion render only (no FFmpeg fallback)
    remotion_out = Path("out_remotion.mp4")
    print("[5] Remotion render", flush=True)
    run(["bash", "-c", "cd remotion && ./node_modules/.bin/remotion render src/index.ts JuraijEdit ../out_remotion.mp4 --props=../remotion-props.json || npx --no-install remotion render src/index.ts JuraijEdit ../out_remotion.mp4 --props=../remotion-props.json"])
    if not remotion_out.exists() or remotion_out.stat().st_size < 1000:
        raise RuntimeError("Remotion produced no output")
    print("REMOTION OK", remotion_out.stat().st_size, flush=True)
    base = remotion_out

    final = Path("out.final.mp4")
    upscale_hdr(base, final, preset="veryfast" if demo else "medium")
    print("FINAL", final.stat().st_size)
    buffer_post("", props["post_caption"], demo)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
