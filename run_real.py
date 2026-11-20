#!/usr/bin/env python3
"""Real end-to-end runner — NO dummy/black/sine fallbacks.

1. Download REAL HD clip + REAL song from YouTube (yt-dlp + YT_COOKIES)
2. Groq Vision 4-corner watermark vet on keyframes
3. Real faster-whisper word-level transcript
4. vicestyle.py renders real montage + real dialogue with real captions
5. meta.py generates savage scene-matched hook for the top bar
If clip or song download fails → exit non-zero with the real error.
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
from pipeline_lib.sourcing import (
    ytdlp_cookie_args, search_queries_for, vet_keyframes_with_groq,
    pick_song_from_bank, yt_song_cmd, GENRE_MOOD,
)


def _run(cmd, timeout=400, check=True):
    print("+", " ".join(str(c) for c in cmd[:10]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-1200:]
        print("FAIL:", err)
        raise RuntimeError(err)
    return r


def download_yt(query: str, out_path: Path, kind: str) -> dict:
    """Download one result. Returns info dict with title/id. Raises on failure."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    info_json = out_path.with_suffix(".info.json")
    cmd = [
        "yt-dlp", "--no-playlist",
        "--js-runtimes", "deno",
        "--extractor-args", "youtube:player_client=web,default",
        "--print-to-file", "title", str(info_json.with_suffix(".title")),
        "--print-to-file", "id", str(info_json.with_suffix(".id")),
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        f"ytsearch1:{query}",
    ]
    cmd += ytdlp_cookie_args()
    _run(cmd, timeout=240)
    if not out_path.exists():
        # yt-dlp may have written with different ext
        candidates = list(out_path.parent.glob(out_path.stem + ".*"))
        real = next((p for p in candidates if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a", ".mp3"}), None)
        if not real:
            raise RuntimeError(f"{kind} download produced no file for query: {query}")
        real.rename(out_path)
    title = ""
    vid = ""
    tfile = info_json.with_suffix(".title")
    ifile = info_json.with_suffix(".id")
    if tfile.exists():
        title = tfile.read_text().strip()
    if ifile.exists():
        vid = ifile.read_text().strip()
    print(f"DOWNLOADED {kind}: title='{title}' id='{vid}' path={out_path}")
    return {"title": title, "id": vid, "path": out_path}


def extract_keyframes(video: Path, n: int = 4) -> list[str]:
    """Extract n frames as base64 for Groq vetting."""
    import base64
    frames = []
    dur = 10.0
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(video)], capture_output=True, text=True, timeout=20)
        dur = float(r.stdout.strip() or 10)
    except Exception:
        pass
    for i in range(n):
        t = max(1.0, dur * (i + 1) / (n + 1))
        img = video.parent / f".kf_{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(video),
                        "-frames:v", "1", "-q:v", "3", str(img)], timeout=30)
        if img.exists():
            frames.append(base64.b64encode(img.read_bytes()).decode())
            img.unlink(missing_ok=True)
    return frames


def whisper_words(path: Path) -> tuple[str, list[dict]]:
    """Return (full_text, word_list with s/e)."""
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), beam_size=1, word_timestamps=True)
    words = []
    texts = []
    for seg in segments:
        texts.append(seg.text.strip())
        for w in (seg.words or []):
            words.append({"word": w.word.strip(), "s": float(w.start), "e": float(w.end)})
    full = " ".join(texts)[:1000]
    print("WHISPER DIALOGUE:", full[:300] or "(none)")
    print(f"WHISPER WORDS: {len(words)}")
    return full, words


def main():
    ensure_queue()
    item = next_ready() or {"id": "demo", "topic": "cinematic movie dialogue scene", "genre": "movies"}
    print("ITEM", item.get("id"), item.get("topic"), item.get("genre"))

    genre = item.get("genre", "movies")
    topic = item.get("topic", "cinematic dialogue scene")

    # Song: songs-bank / local songs/ first, then YouTube with PO Token
    songs_dir = Path("songs")
    songs_dir.mkdir(exist_ok=True)
    song_path = pick_song_from_bank(genre, songs_dir)
    song_info = {"source": "songs-bank", "path": str(song_path)} if song_path else None
    if not song_path:
        song_path = Path("song.mp3")
        song_query = item.get("song_query") or f"{GENRE_MOOD.get(genre, 'epic')} cinematic soundtrack"
        cmd = yt_song_cmd(song_query, song_path)
        try:
            _run(cmd, timeout=240)
            song_info = {"source": "youtube", "query": song_query, "path": str(song_path)}
            print("DOWNLOADED SONG from YouTube:", song_query)
        except Exception as e:
            raise SystemExit(f"SONG DOWNLOAD FAILED — no songs-bank match and YouTube failed: {e}")
    else:
        print("USING SONG FROM BANK:", song_path)

    # Real clip download
    queries = search_queries_for(genre, topic)
    clip_path = Path("clips/clip.mp4")
    clip_info = None
    last_err = None
    for q in queries[:3]:
        try:
            clip_info = download_yt(q, clip_path, "CLIP")
            break
        except Exception as e:
            last_err = e
            print("clip try failed:", e)
    if not clip_info:
        raise SystemExit(f"CLIP DOWNLOAD FAILED — no fallback. Last error: {last_err}")

    # Groq 4-corner vet
    frames = extract_keyframes(clip_path)
    if frames:
        vet = vet_keyframes_with_groq(frames, title=clip_info.get("title", ""), channel="")
        print("GROQ VET:", vet)
        if not vet.get("accept", True):
            raise SystemExit(f"CLIP REJECTED by Groq watermark vet: {vet}")

    # Real Whisper
    transcript, words = whisper_words(clip_path)
    if len(words) < 3:
        print("WARNING: very few Whisper words — continuing with what we have")

    # Savage hook from real transcript
    meta = generate_metadata(topic, genre, transcript)
    if song_info and song_info.get("source") == "songs-bank":
        meta["song_name"] = Path(song_info["path"]).stem
    elif song_info and song_info.get("query"):
        meta["song_name"] = song_info["query"]
    # Ensure credits are present
    if "Clip:" not in meta.get("description", ""):
        meta["description"] = meta.get("description", "").rstrip() + f"\n\nClip: {topic} | Audio: {meta.get('song_name', 'Original Mix')}"
    hook = (meta.get("hook") or topic)[:60]
    print("SAVAGE HOOK:", hook)
    Path("meta.json").write_text(json.dumps(meta, indent=2))
    Path("whisper_words.json").write_text(json.dumps(words))

    # Real render
    out = Path("out.mp4")
    cmd = [sys.executable, "vicestyle.py", "auto",
           "--song", str(song_path), "--clips", "clips",
           "--out", str(out), "--mode", "dual", "--res", "1920x1080",
           "--hook", hook]
    _run(cmd, timeout=900)

    shorts = Path("out.shorts.mp4")
    if not shorts.exists():
        raise SystemExit("RENDER FAILED — out.shorts.mp4 not produced")

    ok, reasons = qc_video(shorts)
    print("QC", ok, reasons)
    if item.get("id") != "demo":
        mark_done(item["id"])
    print("DONE")
    print("SOURCES: clip=", clip_info, "song=", song_info)


if __name__ == "__main__":
    main()
