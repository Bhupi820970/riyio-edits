"""riyio-v2 full: RapidAPI -> Gemini Pass 1 (director) -> cuts -> whisper words -> Remotion draft
-> Gemini Pass 2 (QC inspector) -> 4K HDR upscale -> Buffer."""
from __future__ import annotations
import traceback
import json, os, subprocess, shutil, random, math
from pathlib import Path

from pipeline_lib.gemini_brain import analyze, qc_inspect, available as gemini_ok
from pipeline_lib.audio_sync import detect_beats, whisper_words
from pipeline_lib.sourcing import search_and_download, pick_or_download_song
from pipeline_lib.postprocess import upscale_hdr, buffer_post

NICHE_QUERIES = [
    "Interstellar docking scene 4K",
    "The Dark Knight interrogation scene",
    "Peaky Blinders iconic scene",
    "Oppenheimer Trinity test scene",
    "John Wick nightclub fight scene",
    "Gladiator Are you not entertained",
    "Game of Thrones Rains of Castamere",
    "Breaking Bad I am the one who knocks",
    "Stranger Things upside down scene",
    "Money Heist Bella Ciao scene",
    "Attack on Titan Eren transformation",
    "Solo Leveling Jinwoo shadow",
    "Jujutsu Kaisen Gojo domain",
    "Naruto vs Pain scene",
    "La La Land planetarium scene",
    "Titanic I'm flying scene",
    "The Notebook rain kiss",
    "Champions League iconic goal",
    "Formula 1 overtake radio",
]

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


FPS = 30
MIN_WORDS = 5          # fewer words = captionless video -> reject / shift
INTRO_SKIP = 15.0      # never dialogue_start < 15s on sources longer than 60s
MAX_QC_RETRIES = 2
MAX_CANDIDATES = 4


class CandidateRejected(RuntimeError):
    pass


def min_start(dur):
    return INTRO_SKIP if dur > 60 else 0.0


def find_speech_window(src, dur, avoid_start, length=18.0, scan=300.0):
    """Transcribe up to `scan` seconds after the intro and return the densest-speech window."""
    lo = min_start(dur)
    hi = min(dur, lo + scan)
    if hi - lo < 6:
        return None
    wav = Path("clips/scan.wav")
    run(["ffmpeg", "-y", "-ss", f"{lo:.2f}", "-t", f"{hi - lo:.2f}", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    ws = whisper_words(wav)
    print("SCAN words", len(ws), f"in {lo:.0f}-{hi:.0f}s", flush=True)
    if len(ws) < MIN_WORDS:
        return None
    best, best_n = None, 0
    for i, w in enumerate(ws):
        start = max(0.0, w["s"] - 0.3)
        end = start + length
        n = sum(1 for x in ws[i:] if x["e"] <= end)
        if n > best_n:
            best, best_n = (lo + start, lo + min(end, hi - lo)), n
    if best_n < MIN_WORDS:
        return None
    return best


def beat_action_len(beats):
    """Action clip length synced to beats, clamped 0.5-0.8s."""
    tempo = _num(beats.get("tempo"), 120) or 120
    interval = 60.0 / max(40.0, min(tempo, 240.0))
    best = min((k * interval for k in range(1, 5)),
               key=lambda d: 0 if 0.5 <= d <= 0.8 else min(abs(d - 0.5), abs(d - 0.8)))
    return max(0.5, min(0.8, best))


def build_draft(query, used_urls, demo, cand):
    """One full candidate: download -> Pass 1 -> cuts -> words -> render draft. Returns ctx dict."""
    print(f"=== CANDIDATE {cand}: {query}", flush=True)
    Path("clips").mkdir(exist_ok=True)
    src = Path("clips/source.mp4")
    src.unlink(missing_ok=True)
    info = search_and_download(query, src, exclude=used_urls)
    if not info:
        raise CandidateRejected("no download (RapidAPI)")
    used_urls.add(info.get("url", ""))
    print("DOWNLOADED", info.get("title"), info.get("channel"), flush=True)

    prev = Path("preview360.mp4")
    run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", str(prev)])

    print("[2] Gemini Pass 1 (director)", flush=True)
    plan = analyze(prev) if gemini_ok() else {
        "dialogue_start": 15, "dialogue_end": 33, "action_cuts": [],
        "mood": "dark_hype", "hook": "She read him cold",
        "caption_y": "lower-center",
    }
    if plan.get("reject"):
        reason = plan.get("reject_reason") or "unspecified"
        raise CandidateRejected("Gemini Pass 1 rejected: " + str(reason))
    if not plan.get("post_caption"):
        plan["post_caption"] = f"Clip: {info.get('title','')} | Credit: {info.get('channel','')} | Edited under Fair Use."

    print("[3] FFmpeg cuts", flush=True)
    dur = probe_duration(src)
    print("source duration", dur, flush=True)
    lo = min_start(dur)
    ds = _num(plan.get("dialogue_start"), lo)
    de = _num(plan.get("dialogue_end"), ds + 18)
    if ds < lo:  # hard rule: no YouTube intros
        shift = lo - ds
        ds, de = lo, de + shift
    ds = max(lo, min(ds, max(lo, dur - 12)))
    if de <= ds + 3:
        de = min(dur, ds + 18)
    de = min(de, dur, ds + 25)
    if de <= ds + 0.8:
        raise CandidateRejected(f"cannot cut dialogue: ds={ds} de={de} dur={dur}")
    dlg = Path("clips/dialogue.mp4")
    ffmpeg_cut(src, dlg, ds, de - ds, audio=True)

    words = whisper_words(dlg)
    print("WORDS", len(words), f"window {ds:.1f}-{de:.1f}s", flush=True)
    if len(words) < MIN_WORDS:
        print("too few words -> shifting to highest-speech segment", flush=True)
        win = find_speech_window(src, dur, ds)
        if not win:
            raise CandidateRejected(f"no speech segment with >= {MIN_WORDS} words")
        ds, de = win
        ffmpeg_cut(src, dlg, ds, de - ds, audio=True)
        words = whisper_words(dlg)
        print("WORDS", len(words), f"window {ds:.1f}-{de:.1f}s (shifted)", flush=True)
        if len(words) < MIN_WORDS:
            raise CandidateRejected(f"only {len(words)} words after shift")
    plan["dialogue_start"], plan["dialogue_end"] = round(ds, 2), round(de, 2)

    dlg_dur = probe_duration(dlg)
    dialogue_frames = max(1, int(math.floor(dlg_dur * FPS)))

    song = pick_or_download_song(plan.get("mood", "dark_hype"), Path("songs"), Path("clips/song.mp3"))
    beats = detect_beats(song) if song and song.exists() else {"tempo": 120.0, "beats": [], "drop": 12.0}
    drop_s = _num(beats.get("drop"), 12)
    bl = [b for b in (beats.get("beats") or []) if isinstance(b, (int, float))]
    if bl:
        drop_s = min(bl, key=lambda b: abs(b - drop_s))  # snap drop onto a real beat
    act_len = beat_action_len(beats)

    # action cuts: 5-6 clips, never inside the intro
    raw = []
    for t in plan.get("action_cuts", []) or []:
        try:
            raw.append(float(t))
        except Exception:
            pass
    n = 6 if len(raw) >= 6 else 5
    starts = [t for t in raw if lo <= t <= dur - act_len][:n]
    if len(starts) < n:
        a, b = max(lo, de + 1.0), dur - act_len - 0.1
        if b - a < n:
            a, b = lo, dur - act_len - 0.1
        step = (b - a) / (n + 1)
        fill = [a + step * (k + 1) for k in range(n)]
        starts += [t for t in fill if all(abs(t - s) > 1.0 for s in starts)][: n - len(starts)]
    action_paths, action_frames = [], []
    for i, start in enumerate(starts[:6]):
        ap = Path(f"clips/action_{i}.mp4")
        ffmpeg_cut(src, ap, start, act_len, audio=False)
        fr = int(math.floor(probe_duration(ap) * FPS))
        if fr < 1:
            continue
        action_paths.append(ap)
        action_frames.append(min(fr, int(round(0.8 * FPS))))

    # song alignment: song's beat drop lands exactly on the dialogue end
    drop_frame_song = int(round(drop_s * FPS))
    song_trim = max(0, drop_frame_song - dialogue_frames)
    song_delay = max(0, dialogue_frames - drop_frame_song)
    total = dialogue_frames + sum(action_frames)

    assets_dir = Path("remotion/public/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    for f in assets_dir.glob("*"):
        f.unlink(missing_ok=True)
    shutil.copy(dlg, assets_dir / "dialogue.mp4")
    rel_actions = []
    for i, ap in enumerate(action_paths):
        shutil.copy(ap, assets_dir / f"action_{i}.mp4")
        rel_actions.append(f"assets/action_{i}.mp4")
    rel_song = ""
    if song and song.exists():
        shutil.copy(song, assets_dir / "song.mp3")
        rel_song = "assets/song.mp3"

    props = {
        "hook": plan.get("hook", "She read him cold"),
        "dialogueSrc": "assets/dialogue.mp4",
        "dialogueFrames": dialogue_frames,
        "actionClips": rel_actions,
        "actionFrames": action_frames,
        "words": words,
        "songSrc": rel_song,
        "songTrimBefore": song_trim,
        "songDelay": song_delay,
        "beatDropFrame": dialogue_frames,
        "durationInFrames": total,
        "post_caption": plan.get("post_caption", ""),
    }
    Path("remotion-props.json").write_text(json.dumps(props, indent=2))
    Path("plan.json").write_text(json.dumps({**plan, "source": info, "song": getattr(song, "name", None),
                                             "song_drop_s": drop_s, "tempo": beats.get("tempo")}, indent=2, default=str))
    print("PROPS", len(words), "words,", len(rel_actions), "actions", action_frames, "dialogueFrames", dialogue_frames,
          "total", total, "songDrop", round(drop_s, 2), "trim", song_trim, "delay", song_delay, flush=True)

    print("[5] Remotion render (draft)", flush=True)
    draft = Path("out_remotion.mp4")
    draft.unlink(missing_ok=True)
    run(["bash", "-c", "cd remotion && ./node_modules/.bin/remotion render src/index.ts JuraijEdit ../out_remotion.mp4 --props=../remotion-props.json || npx --no-install remotion render src/index.ts JuraijEdit ../out_remotion.mp4 --props=../remotion-props.json"])
    if not draft.exists() or draft.stat().st_size < 1000:
        raise RuntimeError("Remotion produced no output")
    print("REMOTION OK", draft.stat().st_size, "dur", probe_duration(draft), "expected", round(total / FPS, 2), flush=True)
    return {"draft": draft, "props": props, "plan": plan, "info": info}


def next_query(tried):
    env_q = os.environ.get("QUERY")
    if env_q and env_q not in tried:
        return env_q
    pool = [q for q in NICHE_QUERIES if q not in tried] or NICHE_QUERIES
    return random.choice(pool)


def build_with_candidates(tried, used_urls, demo):
    last = None
    for cand in range(1, MAX_CANDIDATES + 1):
        q = next_query(tried)
        tried.add(q)
        try:
            return build_draft(q, used_urls, demo, cand)
        except CandidateRejected as e:
            last = e
            print("CANDIDATE REJECTED:", e, flush=True)
    raise RuntimeError(f"no usable candidate after {MAX_CANDIDATES} tries: {last}")


def trim_video(src, dest, trim_start, trim_end):
    d = probe_duration(src)
    ts = max(0.0, min(trim_start, d / 3))
    te = max(0.0, min(trim_end, d / 3))
    run(["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-t", f"{d - ts - te:.2f}", "-i", str(src),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(dest)])
    return dest


def main():
    demo = os.environ.get("DEMO_ONLY", "false").lower() in ("1", "true", "yes")
    print("DEMO", demo, "GEMINI", gemini_ok(), flush=True)
    tried, used_urls = set(), set()
    ctx = build_with_candidates(tried, used_urls, demo)
    draft = ctx["draft"]

    verdict = None
    for attempt in range(MAX_QC_RETRIES + 1):
        print(f"[6] Gemini Pass 2 (QC) attempt {attempt + 1}", flush=True)
        qc360 = Path("draft360.mp4")
        run(["ffmpeg", "-y", "-i", str(draft), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", str(qc360)])
        verdict = qc_inspect(qc360)
        print("QC PASS2 JSON:", json.dumps(verdict), flush=True)
        Path("qc.json").write_text(json.dumps(verdict, indent=2))
        if verdict.get("qc_error"):
            raise RuntimeError("Gemini Pass 2 unavailable: " + verdict["qc_error"])
        if verdict.get("pass"):
            break
        if attempt == MAX_QC_RETRIES:
            raise RuntimeError(f"QC failed after {MAX_QC_RETRIES} retries: {verdict.get('issues')}")
        ts, te = _num(verdict.get("trim_start"), 0), _num(verdict.get("trim_end"), 0)
        if not verdict.get("retry_new_clip") and (ts > 0 or te > 0):
            print(f"QC -> trim start {ts}s end {te}s", flush=True)
            draft = trim_video(draft, Path(f"draft_trim{attempt}.mp4"), ts, te)
        else:
            print("QC -> retry with a fresh clip", flush=True)
            ctx = build_with_candidates(tried, used_urls, demo)
            draft = ctx["draft"]

    if draft != Path("out_remotion.mp4"):
        shutil.copy(draft, "out_remotion.mp4")
    print("[7] 4K HDR upscale 2160x2700", flush=True)
    final = Path("out.final.mp4")
    upscale_hdr(draft, final, preset="veryfast" if demo else "medium")
    print("FINAL", final.stat().st_size, "dur", probe_duration(final), flush=True)
    buffer_post("", ctx["props"]["post_caption"], demo)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
