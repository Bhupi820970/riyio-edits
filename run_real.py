#!/usr/bin/env python3
"""Real end-to-end runner — NO dummy/black/sine fallbacks.

1. Song from songs-bank release only; clips via RapidAPI (YouTube) / yt-dlp (X)
2. Clean-content vet (Groq vision, heuristic fallback): no watermarks/face-cams/
   corner logos/scoreboards/streamer overlays; prefer longer coherent sources
3. Real faster-whisper word-level transcript (small model for better accuracy)
4. vicestyle.py renders real montage + real dialogue with real captions
5. meta.py generates savage scene-matched hook for the top bar
If clip or song download fails → exit non-zero with the real error.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline_lib.queue_manager import next_ready, mark_done, ensure_queue, load_history
from pipeline_lib.meta import generate_metadata
from pipeline_lib.qc import qc_video
from pipeline_lib.sourcing import (
    search_queries_for, vet_keyframes_with_groq, ensure_song_from_bank, song_credit,
    rapid_available, rapid_search, rapid_download, title_is_clean, youtube_id,
    MIN_CLIP_S, MAX_CLIP_SEARCH_S,
)
from pipeline_lib.links import load_clip_links


def _run(cmd, timeout=400, check=True):
    print("+", " ".join(str(c) for c in cmd[:10]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-1200:]
        print("FAIL:", err)
        raise RuntimeError(err)
    return r


def download_yt(query_or_url: str, out_path: Path, kind: str) -> dict:
    """yt-dlp download for NON-YouTube links (e.g. X). YouTube goes via RapidAPI."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tfile = out_path.with_suffix(".title")
    ifile = out_path.with_suffix(".id")
    cmd = ["yt-dlp", "--no-playlist", "--print-to-file", "title", str(tfile),
           "--print-to-file", "id", str(ifile),
           "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
           "-o", str(out_path), query_or_url]
    _run(cmd, timeout=240)
    if not out_path.exists():
        real = next((p for p in out_path.parent.glob(out_path.stem + ".*")
                     if p.suffix.lower() in {".mp4", ".mkv", ".webm"}), None)
        if not real:
            raise RuntimeError(f"{kind} download produced no file")
        real.rename(out_path)
    title = tfile.read_text().strip() if tfile.exists() else ""
    vid = ifile.read_text().strip() if ifile.exists() else ""
    tfile.unlink(missing_ok=True)
    ifile.unlink(missing_ok=True)
    return {"title": title, "id": vid, "path": out_path, "source": query_or_url}


def probe_dur(p: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(p)], capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


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
    """Return (full_text, word_list with s/e).

    Uses 'small' model (better accuracy than base) with higher beam and VAD
    for cleaner word-level timestamps. Falls back to base if small fails.
    """
    from faster_whisper import WhisperModel
    model_name = "small"
    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception:
        print("small model unavailable, falling back to base")
        model_name = "base"
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    print(f"WHISPER model={model_name}")
    segments, info = model.transcribe(
        str(path),
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        condition_on_previous_text=False,
        language="en",
    )
    words = []
    texts = []
    for seg in segments:
        txt = (seg.text or "").strip()
        if txt:
            texts.append(txt)
        for w in (seg.words or []):
            word = (w.word or "").strip()
            if not word or len(word) < 1:
                continue
            # Drop very low confidence if available
            prob = getattr(w, "probability", 1.0) or 1.0
            if prob < 0.35:
                continue
            words.append({"word": word, "s": float(w.start), "e": float(w.end)})
    full = " ".join(texts)[:1000]
    print("WHISPER DIALOGUE:", full[:300] or "(none)")
    print(f"WHISPER WORDS: {len(words)}")
    return full, words


def _title_core(title: str) -> str:
    """Extract a rough movie/series core for same-source matching."""
    t = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    t = re.sub(r"\b(best|dialogue|dialogues|scene|scenes|official|clip|4k|hd|full|movie|film|series|episode|ep)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:60]


def _same_source(a: str, b: str) -> bool:
    ca, cb = _title_core(a), _title_core(b)
    if not ca or not cb:
        return False
    # Strong overlap of meaningful words
    sa, sb = set(ca.split()), set(cb.split())
    if not sa or not sb:
        return False
    inter = sa & sb
    return len(inter) >= 2 and (len(inter) / min(len(sa), len(sb))) >= 0.45


def gather_clips(genre: str, topic: str, used_ids: set[str], want_total: float = 90.0,
                 max_clips: int = 2, max_tries: int = 8) -> list[dict]:
    """Collect clean footage preferring ONE coherent movie/series.

    Strategy:
    1. Search and rank longer clean candidates.
    2. Accept the best long primary source first.
    3. Only accept a second clip if its title strongly matches the primary (same movie/series).
    4. Prefer cutting many short non-overlapping shots from the primary long source.
    """
    cands: list[dict] = []
    for link in load_clip_links(genre=genre):
        vid = youtube_id(link) or link.rstrip("/").split("/")[-1]
        if vid not in used_ids:
            cands.append({"url": link, "id": vid, "title": "", "channel": "", "duration": 0.0,
                          "via": "rapidapi" if youtube_id(link) else "yt-dlp"})
    if rapid_available():
        seen = set()
        for q in search_queries_for(genre, topic)[:5]:
            try:
                res = rapid_search(q)
            except Exception as e:
                print("search failed:", str(e)[:160])
                continue
            print(f"SEARCH '{q}': {len(res)} results")
            for v in res:
                if not v["id"] or v["id"] in used_ids or v["id"] in seen:
                    continue
                seen.add(v["id"])
                if not (40.0 <= v["duration"] <= 300.0):
                    continue
                ok, why = title_is_clean(v["title"], v["channel"])
                if not ok:
                    print("  skip (title):", v["title"][:60], "|", why)
                    continue
                v["via"] = "rapidapi"
                cands.append(v)
    else:
        print("WARNING: no YT_RAPIDAPI_KEY_* — only non-YouTube links can be used")

    # Prefer longer sources first
    cands.sort(key=lambda c: -c.get("duration", 0))

    got: list[dict] = []
    primary_title = ""
    tries = 0
    for c in cands:
        if len(got) >= max_clips or sum(g["dur"] for g in got) >= want_total or tries >= max_tries:
            break
        tries += 1
        # After first clip, only accept strongly matching same-source titles
        if got and not _same_source(primary_title, c.get("title", "")):
            print("  skip (different source):", c.get("title", "")[:70])
            continue
        out = Path("clips") / f"clip{len(got) + 1}.mp4"
        out.unlink(missing_ok=True)
        try:
            if c["via"] == "rapidapi":
                d = c.get("duration") or 0.0
                st = en = None
                if d > 100:
                    st = max(15.0, d * 0.1)
                    en = min(st + 85.0, d - 8)
                info = rapid_download(c["url"], "1080", out, start=st, end=en)
                title = c.get("title") or info.get("title", "")
            else:
                info = download_yt(c["url"], out, "CLIP")
                title = info.get("title", "")
        except Exception as e:
            print("  download failed:", c["url"][:80], str(e)[:160])
            out.unlink(missing_ok=True)
            continue
        dur = probe_dur(out)
        if dur < 28:
            print(f"  REJECT too short ({dur:.1f}s): {title[:60]}")
            out.unlink(missing_ok=True)
            continue
        frames = extract_keyframes(out, n=5)
        vet = vet_keyframes_with_groq(frames, title=title, channel=c.get("channel", ""), video=out)
        print(f"  VET [{vet.get('by')}] accept={vet.get('accept')} :: {vet.get('reason')}")
        if not vet.get("accept"):
            out.unlink(missing_ok=True)
            continue
        print(f"  ACCEPT clip {out.name}: {dur:.1f}s '{title[:70]}' id={c['id']}")
        got.append({"path": out, "dur": dur, "title": title, "id": c["id"], "url": c["url"]})
        if not primary_title:
            primary_title = title
    return got


def main():
    ensure_queue()
    item = next_ready() or {"id": "demo", "topic": "cinematic movie dialogue scene", "genre": "movies"}
    print("ITEM", item.get("id"), "|", item.get("genre"))
    genre = item.get("genre", "movies")
    topic = item.get("topic", "cinematic dialogue scene")
    hist = load_history()
    used_ids = set(hist.get("source_ids", []))

    # Song: ONLY from songs-bank release (no stock/dummy audio anywhere).
    song_mp3, song_entry = ensure_song_from_bank(genre, Path("song.mp3"), used=set(hist.get("songs", [])))
    credit = song_credit(song_entry, song_mp3)
    song_wav = Path("song.wav")
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(song_mp3), "-ac", "2", "-ar", "48000", str(song_wav)])
    print("AUDIO SOURCE: songs-bank/" + song_entry["file"], "|", credit)

    # Clips: prefer one coherent long source so auto_plan can cut many short distinct scenes
    shutil.rmtree("clips", ignore_errors=True)
    Path("clips").mkdir()
    clips = gather_clips(genre, topic, used_ids)
    total = sum(c["dur"] for c in clips)
    print(f"CLIPS: {len(clips)} accepted, {total:.1f}s unique footage: "
          + ", ".join(f"{c['path'].name}={c['dur']:.1f}s" for c in clips))
    if not clips or total < 35:
        raise SystemExit(f"NOT ENOUGH CLEAN FOOTAGE ({total:.1f}s) — refusing to loop short clips")

    # Real Whisper on every clip -> per-clip word map for full captions.
    wmap, transcript = {}, []
    for c in clips:
        t, words = whisper_words(c["path"])
        wmap[str(c["path"])] = words
        transcript.append(t)
    Path("whisper_words.json").write_text(json.dumps(wmap))

    meta = generate_metadata(topic, genre, " ".join(transcript), song_credit=credit,
                             item_id=str(item.get("id", "")))
    meta["sources"] = [{"title": c["title"], "url": c["url"]} for c in clips]
    hook = meta["hook"]
    print("SAVAGE HOOK:", hook, f"(source={meta.get('hook_source')})")
    Path("meta.json").write_text(json.dumps(meta, indent=2))

    out = Path("out.mp4")
    _run([sys.executable, "vicestyle.py", "auto", "--song", str(song_wav), "--clips", "clips",
          "--out", str(out), "--mode", "dual", "--res", "1920x1080", "--hook", hook], timeout=1500)
    shorts = Path("out.shorts.mp4")
    if not shorts.exists():
        raise SystemExit("RENDER FAILED — out.shorts.mp4 not produced")
    rep = json.loads(Path("out.mp4.json").read_text()) if Path("out.mp4.json").exists() else {}
    print("RENDER REPORT:", json.dumps({k: rep.get(k) for k in
          ("duration", "shots", "captions", "dialogue_s", "hook")}))
    print("CAPTIONS:", " | ".join(rep.get("caption_text", [])[:60]))
    print("SEGMENTS:", json.dumps(rep.get("segments", [])))

    ok, reasons = qc_video(shorts)
    print("QC", ok, reasons)
    if item.get("id") != "demo":
        mark_done(item["id"], source_ids=[c["id"] for c in clips], song=song_entry["file"])
    print("DONE")


if __name__ == "__main__":
    main()
