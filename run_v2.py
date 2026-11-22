"""riyio-v2 (RIYIO reference style, docs/REFERENCE_STYLE.md):
RapidAPI -> Gemini Pass 1 (director) -> graded no-crop 4:5 cuts -> whisper words (English) -> Remotion draft
-> Gemini Pass 2 (QC inspector) -> 4K upscale -> Buffer."""
from __future__ import annotations
import traceback
import json, os, subprocess, shutil, random, math
from pathlib import Path

from pipeline_lib.gemini_brain import analyze, qc_inspect, available as gemini_ok
from pipeline_lib.audio_sync import detect_beats, whisper_words, detect_language
from pipeline_lib.sourcing import search_and_download, download_bank_song
from pipeline_lib.postprocess import upscale_hdr, buffer_post
from pipeline_lib import style

# Rotating famous-scene bank: iconic ENGLISH dialogue scenes (anime = English dub).
NICHE_QUERIES = [
    "Interstellar Cooper and Murph goodbye scene",
    "The Dark Knight interrogation scene Joker Batman",
    "Peaky Blinders Tommy Shelby speech scene",
    "Oppenheimer Truman office scene",
    "John Wick people keep asking if I'm back scene",
    "Gladiator my name is Maximus scene",
    "Game of Thrones Arya Walder Frey scene",
    "Breaking Bad say my name scene",
    "Stranger Things Eleven Vecna scene",
    "Money Heist Professor speech scene English dub",
    "Attack on Titan Eren speech scene English dub",
    "Solo Leveling Jinwoo arise scene English dub",
    "Jujutsu Kaisen Gojo throughout heaven and earth English dub",
    "Naruto vs Pain conversation scene English dub",
    "La La Land planetarium scene",
    "Titanic I'm flying scene",
    "The Notebook it wasn't over scene",
    "Champions League iconic comeback English commentary",
    "Formula 1 iconic team radio moment",
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


FPS = style.FPS
MIN_WORDS = 8          # fewer words = captionless video -> reject / shift
INTRO_SKIP = 15.0      # never dialogue_start < 15s on sources longer than 60s
MAX_QC_RETRIES = 2
MAX_CANDIDATES = 5
END_CARD_S = 2.0
DLG_MIN, DLG_MAX = 28.0, 46.0     # phase 1 (dialogue) seconds
TOTAL_MIN, TOTAL_MAX = 35.0, 59.0
BED_GAIN = 0.28                   # ~ -11 dB under the dialogue
BED_SONGS = {"emotional_romance": ["epic_4.mp3", "epic_7.mp3"],
             "default": ["epic_5.mp3", "epic_4.mp3", "dark_6.mp3", "dark_4.mp3"]}
DROP_SONGS = {"emotional_romance": ["epic_2.mp3", "aggressive_2.mp3"],
              "default": ["aggressive_2.mp3", "aggressive_3.mp3", "aggressive_1.mp3", "dark_3.mp3", "dark_1.mp3"]}


class CandidateRejected(RuntimeError):
    pass


def min_start(dur):
    return INTRO_SKIP if dur > 60 else 0.0


def probe_video(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "json", str(path)], capture_output=True, text=True)
    try:
        st = json.loads(r.stdout)["streams"][0]
        return int(st["width"]), int(st["height"])
    except Exception:
        return 0, 0


def prep_cut(src, dest, start, duration, audio=True, rgb=False, preset="fast"):
    """Graded, sharpened, no-crop 4:5 cut (blurred fill top/bottom). Dialogue audio loudness-normalised."""
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
           "-filter_complex", style.frame_filter(rgb), "-map", "[v]",
           "-c:v", "libx264", "-preset", preset, "-crf", "14", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if audio:
        cmd += ["-map", "0:a:0?", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd.append(str(dest))
    run(cmd)
    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError(f"cut produced no file: {dest}")


def extract_wav(src, dest, start, duration):
    run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dest)])
    return dest


def make_sfx(assets_dir):
    """Self-generated SFX (no downloads): low boom hit + noise whoosh."""
    hit, whoosh = assets_dir / "hit.wav", assets_dir / "whoosh.wav"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i",
         "aevalsrc='0.9*sin(2*PI*(45+110*exp(-t*22))*t)*exp(-t*6)':s=48000:d=0.7",
         "-af", "afade=t=out:st=0.5:d=0.2", "-ac", "2", str(hit)])
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.45:c=pink:r=48000:a=0.6",
         "-af", "highpass=f=700,lowpass=f=7000,afade=t=in:d=0.28:curve=exp,afade=t=out:st=0.28:d=0.17", "-ac", "2", str(whoosh)])
    return hit, whoosh


def find_speech_window(src, dur, length=40.0, scan=240.0):
    """Transcribe up to `scan` seconds after the intro and return the densest-speech window."""
    lo = min_start(dur)
    hi = min(dur, lo + scan)
    if hi - lo < DLG_MIN:
        return None
    ws = whisper_words(extract_wav(src, Path("clips/scan.wav"), lo, hi - lo))
    print("SCAN words", len(ws), f"in {lo:.0f}-{hi:.0f}s", flush=True)
    if len(ws) < MIN_WORDS:
        return None
    best, best_n = None, 0
    for i, w in enumerate(ws):
        start = max(0.0, w["s"] - 1.0)
        end = start + length
        n = sum(1 for x in ws[i:] if x["e"] <= end)
        if n > best_n:
            best, best_n = (lo + start, lo + min(end, hi - lo)), n
    if best_n < MIN_WORDS:
        return None
    return best


def transcribe_window(src, ds, length):
    wav = extract_wav(src, Path("clips/dialogue.wav"), ds, length)
    lang, prob = detect_language(wav)
    print(f"LANG {lang} p={prob:.2f}", flush=True)
    if lang not in ("en", "?") and prob > 0.5:
        raise CandidateRejected(f"not English ({lang} p={prob:.2f})")
    words = whisper_words(wav, language="en")
    print("WORDS", len(words), f"window {ds:.1f}-{ds + length:.1f}s", flush=True)
    return words, lang


def pick_song(pool, mood, out):
    files = list(pool.get(mood) or pool["default"])
    random.shuffle(files)
    for f in files + pool["default"]:
        got = download_bank_song(f, out)
        if got:
            return got, f
    return None, None


def build_draft(query, used_urls, demo, cand):
    """One full candidate: download -> Pass 1 -> words -> cuts -> render draft. Returns ctx dict."""
    print(f"=== CANDIDATE {cand}: {query}", flush=True)
    Path("clips").mkdir(exist_ok=True)
    src = Path("clips/source.mp4")
    src.unlink(missing_ok=True)
    info = search_and_download(query, src, exclude=used_urls)
    if not info:
        raise CandidateRejected("no download (RapidAPI)")
    used_urls.add(info.get("url", ""))
    dur = probe_duration(src)
    w, h = probe_video(src)
    print("DOWNLOADED", info.get("title"), "|", info.get("channel"), f"{w}x{h}", f"{dur:.1f}s", flush=True)
    if min(w, h) < 700:
        raise CandidateRejected(f"source too low-res {w}x{h}")
    if dur < DLG_MIN + 15:
        raise CandidateRejected(f"source too short ({dur:.0f}s)")

    prev = Path("preview360.mp4")
    run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", str(prev)])

    print("[2] Gemini Pass 1 (director)", flush=True)
    plan = analyze(prev) if gemini_ok() else {"dialogue_start": 15, "dialogue_end": 50, "action_cuts": [], "mood": "dark_hype"}
    if plan.get("reject"):
        raise CandidateRejected("Gemini Pass 1 rejected: " + str(plan.get("reject_reason") or "unspecified"))
    if str(plan.get("language") or "en").lower()[:2] != "en":
        raise CandidateRejected(f"Gemini says language={plan.get('language')}")
    lo = min_start(dur)

    # ---- dialogue window (phase 1) ----
    ds = max(lo, _num(plan.get("dialogue_start"), lo))
    de = min(dur - 0.5, _num(plan.get("dialogue_end"), ds + 40))
    punch_abs = plan.get("punch_time")
    punch_abs = _num(punch_abs, de - 1) if punch_abs not in (None, "") else None
    if punch_abs is not None and ds < punch_abs < dur:
        de = max(de, punch_abs + 1.0)
    if de - ds < DLG_MIN + 1:
        ds = max(lo, de - (DLG_MIN + 3))
    if de - ds > DLG_MAX + 2:
        ds = de - (DLG_MAX + 1)
    if de - ds < 20:
        raise CandidateRejected(f"dialogue window too short {ds:.1f}-{de:.1f}")
    win_len = min(dur - ds, de - ds + 1.5)
    words, lang = transcribe_window(src, ds, win_len)
    if len(words) < MIN_WORDS:
        print("too few words -> shifting to highest-speech segment", flush=True)
        win = find_speech_window(src, dur)
        if not win:
            raise CandidateRejected(f"no speech segment with >= {MIN_WORDS} words")
        ds, de = win
        punch_abs = None
        win_len = de - ds
        words, lang = transcribe_window(src, ds, win_len)
        if len(words) < MIN_WORDS:
            raise CandidateRejected(f"only {len(words)} words after shift")

    pidx = style.find_punch(words, plan.get("punch_word", ""), (punch_abs - ds) if punch_abs is not None else None)
    punch_s, punch_e = words[pidx]["s"], words[pidx]["e"]
    if punch_e + 0.3 < DLG_MIN and ds > lo + 0.5:
        # pull the start earlier so phase 1 is long enough, then re-transcribe
        new_ds = max(lo, ds - (DLG_MIN - punch_e + 0.5))
        shift = ds - new_ds
        ds = new_ds
        words, lang = transcribe_window(src, ds, win_len + shift)
        pidx = style.find_punch(words, plan.get("punch_word", ""), punch_s + shift)
        punch_s, punch_e = words[pidx]["s"], words[pidx]["e"]
    if punch_e + 0.3 > DLG_MAX:
        shift = punch_e + 0.3 - DLG_MAX
        ds += shift
        words = [{**x, "s": x["s"] - shift, "e": x["e"] - shift} for x in words if x["s"] - shift >= 0.05]
        pidx = style.find_punch(words, plan.get("punch_word", ""), punch_s - shift)
        punch_s, punch_e = words[pidx]["s"], words[pidx]["e"]
    print(f"PUNCH '{words[pidx]['word']}' at {punch_s:.2f}-{punch_e:.2f}s (window start {ds:.2f})", flush=True)

    # ---- music: dark bed (ducked) + phonk/epic drop on the punch word ----
    mood = plan.get("mood") or "dark_hype"
    bed, bed_name = pick_song(BED_SONGS, mood, Path("clips/bed.mp3"))
    drop, drop_name = pick_song(DROP_SONGS, mood, Path("clips/drop.mp3"))
    beats = detect_beats(drop) if drop else {"tempo": 120.0, "beats": [], "drop": 0.0}
    song_drop = _num(beats.get("drop"), 0.0)
    bl = sorted(b for b in (beats.get("beats") or []) if isinstance(b, (int, float)))
    if bl:
        song_drop = min(bl, key=lambda b: abs(b - song_drop))
    beats_comp = [punch_s + (b - song_drop) for b in bl if b >= song_drop]
    if len(beats_comp) < 8:
        iv = 60.0 / max(60.0, _num(beats.get("tempo"), 120))
        beats_comp = [punch_s + k * iv for k in range(80)]

    # phase 1 ends on the first kick after the punch word
    D = punch_e + 0.25
    nxt = [b for b in beats_comp if punch_e + 0.1 <= b <= punch_e + 0.7]
    if nxt:
        D = nxt[0]
    M = max(round(D * 0.22, 2), TOTAL_MIN + 1.5 - D - END_CARD_S)
    M = min(max(M, 5.0), 13.0, TOTAL_MAX - D - END_CARD_S)
    if M < 4.0 or D + M + END_CARD_S < TOTAL_MIN:
        raise CandidateRejected(f"cannot fit 35-60s (dialogue {D:.1f}s)")
    cuts = style.montage_cuts(beats_comp, D, M)

    print("[3] FFmpeg graded cuts", flush=True)
    dlg = Path("clips/dialogue.mp4")
    prep_cut(src, dlg, ds, D + 0.3, audio=True, preset="medium")
    dialogue_frames = min(int(round(D * FPS)), int(math.floor(probe_duration(dlg) * FPS)))
    drop_frame = int(round(punch_s * FPS))

    # montage source times: Gemini's picks outside the dialogue, then even fill
    used_lo, used_hi = ds - 0.5, ds + D + 0.5
    picks = []
    for t in plan.get("action_cuts") or []:
        try:
            t = float(t)
        except Exception:
            continue
        if lo <= t <= dur - 1.0 and not (used_lo <= t <= used_hi) and all(abs(t - p) > 0.6 for p in picks):
            picks.append(t)
    k = 0
    base = list(picks)
    while len(picks) < len(cuts) and base and k < 6:
        k += 1
        for t in base:
            t2 = t + 1.1 * k
            if t2 <= dur - 1.0 and not (used_lo <= t2 <= used_hi) and all(abs(t2 - p) > 0.6 for p in picks):
                picks.append(t2)
    if len(picks) < len(cuts):
        span = [x * 0.5 for x in range(int(lo * 2), int((dur - 1) * 2))]
        span = [t for t in span if not (used_lo <= t <= used_hi) and all(abs(t - p) > 0.6 for p in picks)]
        step = max(1, len(span) // max(1, len(cuts) - len(picks) + 1))
        picks += span[step::step][: len(cuts) - len(picks)]
    action_paths, action_frames = [], []
    cursor = dialogue_frames / FPS
    for i, (t, c) in enumerate(zip(picks, cuts)):
        f0, f1 = int(round(cursor * FPS)), int(round((cursor + c) * FPS))
        cursor += c
        want = max(1, f1 - f0)
        ap = Path(f"clips/action_{i}.mp4")
        prep_cut(src, ap, t, want / FPS + 0.1, audio=False, rgb=True)
        fr = min(want, int(math.floor(probe_duration(ap) * FPS)))
        if fr >= 1:
            action_paths.append(ap)
            action_frames.append(fr)
    if len(action_paths) < 5:
        raise CandidateRejected(f"only {len(action_paths)} montage cuts")

    end_frames = int(round(END_CARD_S * FPS))
    total = dialogue_frames + sum(action_frames) + end_frames
    if not (TOTAL_MIN * FPS <= total <= 60 * FPS):
        raise CandidateRejected(f"length {total / FPS:.1f}s outside 35-60s")

    # ---- captions (1-4 words, whisper word timing) + hooks ----
    captions = style.group_captions(words, pidx, dialogue_frames / FPS)
    hook = (plan.get("hook_title") or plan.get("hook") or "").strip().strip('"')
    if not style.good_hook(hook):
        hook = " ".join((plan.get("scene") or info.get("title") or "The Moment").split()[:3])
    hq = (plan.get("hook_question") or "").strip().strip('"')
    if not style.good_hook(hq):
        hq = "WHAT WOULD YOU DO..?"
    plan.update({"hook_title": hook, "hook_question": hq})
    if not plan.get("post_caption"):
        plan["post_caption"] = f"Clip: {info.get('title','')} | Credit: {info.get('channel','')} | Edited under Fair Use."

    assets_dir = Path("remotion/public/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    for f in assets_dir.glob("*"):
        f.unlink(missing_ok=True)
    shutil.copy(dlg, assets_dir / "dialogue.mp4")
    rel_actions = []
    for i, ap in enumerate(action_paths):
        shutil.copy(ap, assets_dir / f"action_{i}.mp4")
        rel_actions.append(f"assets/action_{i}.mp4")
    if bed:
        shutil.copy(bed, assets_dir / "bed.mp3")
    if drop:
        shutil.copy(drop, assets_dir / "drop.mp3")
    make_sfx(assets_dir)

    props = {
        "hook": hook,
        "hookQuestion": hq,
        "dialogueSrc": "assets/dialogue.mp4",
        "dialogueFrames": dialogue_frames,
        "dropFrame": drop_frame,
        "actionClips": rel_actions,
        "actionFrames": action_frames,
        "endFrames": end_frames,
        "captions": captions,
        "bedSrc": "assets/bed.mp3" if bed else "",
        "bedVolume": BED_GAIN,
        "dropSrc": "assets/drop.mp3" if drop else "",
        "dropTrimBefore": int(round(song_drop * FPS)),
        "hitSrc": "assets/hit.wav",
        "whooshSrc": "assets/whoosh.wav",
        "durationInFrames": total,
        "post_caption": plan.get("post_caption", ""),
    }
    Path("remotion-props.json").write_text(json.dumps(props, indent=2))
    meta = {**plan, "source": info, "source_res": f"{w}x{h}", "window_start": round(ds, 2),
            "punch": words[pidx]["word"], "punch_s": round(punch_s, 2), "bed_song": bed_name, "drop_song": drop_name,
            "song_drop_s": round(song_drop, 2), "tempo": beats.get("tempo"), "words": len(words), "language": lang,
            "dialogue_s": round(dialogue_frames / FPS, 2), "montage_s": round(sum(action_frames) / FPS, 2),
            "total_s": round(total / FPS, 2), "captions": len(captions)}
    Path("plan.json").write_text(json.dumps(meta, indent=2, default=str))
    print("PLAN", json.dumps({k: meta[k] for k in ("scene", "punch", "bed_song", "drop_song", "dialogue_s", "montage_s",
                                                  "total_s", "words", "captions", "hook_title", "hook_question")}, default=str), flush=True)

    print("[5] Remotion render (draft)", flush=True)
    draft = Path("out_remotion.mp4")
    draft.unlink(missing_ok=True)
    flags = "--props=../remotion-props.json --jpeg-quality=95 --crf=16 --x264-preset=medium --audio-bitrate=192k"
    run(["bash", "-c", f"cd remotion && ./node_modules/.bin/remotion render src/index.ts JuraijEdit ../out_remotion.mp4 {flags} || npx --no-install remotion render src/index.ts JuraijEdit ../out_remotion.mp4 {flags}"])
    if not draft.exists() or draft.stat().st_size < 1000:
        raise RuntimeError("Remotion produced no output")
    print("REMOTION OK", draft.stat().st_size, "dur", probe_duration(draft), "expected", round(total / FPS, 2), flush=True)
    return {"draft": draft, "props": props, "plan": meta, "info": info}


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
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(dest)])
    return dest


def black_segments(video, until):
    """Local black-frame check (ignores the dark end card)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-t", f"{until:.2f}", "-i", str(video), "-vf",
                        "blackdetect=d=0.2:pix_th=0.08", "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [ln.split("blackdetect")[-1].strip() for ln in r.stderr.splitlines() if "black_start" in ln]


def main():
    demo = os.environ.get("DEMO_ONLY", "false").lower() in ("1", "true", "yes")
    print("DEMO", demo, "GEMINI", gemini_ok(), flush=True)
    tried, used_urls = set(), set()
    ctx = build_with_candidates(tried, used_urls, demo)
    draft = ctx["draft"]

    verdict = None
    for attempt in range(MAX_QC_RETRIES + 1):
        print(f"[6] Gemini Pass 2 (QC) attempt {attempt + 1}", flush=True)
        dlen = probe_duration(draft)
        blacks = black_segments(draft, dlen - END_CARD_S)
        facts = {"duration_s": round(dlen, 2), "language": ctx["plan"].get("language"),
                 "whisper_words": ctx["plan"].get("words"), "caption_groups": ctx["plan"].get("captions"),
                 "dialogue_s": ctx["plan"].get("dialogue_s"), "montage_s": ctx["plan"].get("montage_s"),
                 "end_card_s": END_CARD_S, "black_segments": blacks}
        print("QC FACTS", json.dumps(facts), flush=True)
        qc360 = Path("draft360.mp4")
        run(["ffmpeg", "-y", "-i", str(draft), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", str(qc360)])
        verdict = qc_inspect(qc360, facts)
        local = []
        if not (TOTAL_MIN <= dlen <= 60.0):
            local.append(f"length {dlen:.1f}s outside 35-60s")
        if blacks:
            local.append(f"black frames: {blacks[:3]}")
        if local:
            verdict["pass"] = False
            verdict["issues"] = list(verdict.get("issues") or []) + local
            verdict["retry_new_clip"] = True
        print("QC PASS2 JSON:", json.dumps(verdict), flush=True)
        Path("qc.json").write_text(json.dumps(verdict, indent=2))
        if verdict.get("qc_error"):
            raise RuntimeError("Gemini Pass 2 unavailable: " + verdict["qc_error"])
        if verdict.get("pass"):
            break
        if attempt == MAX_QC_RETRIES:
            raise RuntimeError(f"QC failed after {MAX_QC_RETRIES} retries: {verdict.get('issues')}")
        ts, te = _num(verdict.get("trim_start"), 0), _num(verdict.get("trim_end"), 0)
        if not verdict.get("retry_new_clip") and (ts > 0 or te > 0) and dlen - ts - te >= TOTAL_MIN:
            print(f"QC -> trim start {ts}s end {te}s", flush=True)
            draft = trim_video(draft, Path(f"draft_trim{attempt}.mp4"), ts, te)
        else:
            print("QC -> retry with a fresh clip", flush=True)
            ctx = build_with_candidates(tried, used_urls, demo)
            draft = ctx["draft"]

    if draft != Path("out_remotion.mp4"):
        shutil.copy(draft, "out_remotion.mp4")
    print("[7] 4K upscale 2160x2700", flush=True)
    final = Path("out.final.mp4")
    upscale_hdr(draft, final, preset="slow")
    print("FINAL", final.stat().st_size, "dur", probe_duration(final), flush=True)
    buffer_post("", ctx["props"]["post_caption"], demo)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
