"""riyio-v2 (RIYIO reference style, docs/REFERENCE_STYLE.md):
RapidAPI -> Gemini Pass 1 (director) -> graded no-crop 4:5 cuts -> whisper words (English) -> Remotion draft
-> Gemini Pass 2 (QC inspector) -> 4K upscale -> Buffer."""
from __future__ import annotations
import traceback
import json, os, re, subprocess, shutil, random, math
from pathlib import Path

from pipeline_lib.gemini_brain import analyze, qc_inspect, prescreen, pick_shots, available as gemini_ok
from pipeline_lib.audio_sync import detect_beats, whisper_words, detect_language
from pipeline_lib.sourcing import search_candidates, download_url, download_bank_song
from pipeline_lib.postprocess import upscale_hdr, buffer_post
from pipeline_lib import style
from pipeline_lib import captions as captions_mod
from pipeline_lib import channel_blocklist, link_queue, channel_source
from pipeline_lib import montage_select as msel
from pipeline_lib import song_mood as SM
from pipeline_lib import shot_library as SL

# Rotating famous-scene bank by GENRE: iconic ENGLISH dialogue (anime = English dub; sports/games may use
# English commentary / team radio / cutscene dialogue). GENRE env forces a genre, QUERY env forces a query.
GENRES = {
    "movies": [
        "Interstellar Cooper and Murph goodbye scene",
        "The Dark Knight interrogation scene Joker Batman",
        "Oppenheimer Truman office scene",
        "John Wick people keep asking if I'm back scene",
        "Gladiator my name is Maximus scene",
        "The Wolf of Wall Street sell me this pen scene",
        "Joker 2019 Murray Franklin show scene",
        "Fight Club rules of fight club scene",
    ],
    "web_series": [
        "Peaky Blinders Tommy Shelby speech scene",
        "Game of Thrones Arya Walder Frey scene",
        "Breaking Bad say my name scene",
        "Stranger Things Eleven Vecna scene",
        "Suits Harvey Specter iconic scene",
        "The Boys Homelander iconic scene",
        "House of the Dragon Daemon iconic scene",
        "Money Heist Professor speech scene English dub",
    ],
    "games": [
        "Red Dead Redemption 2 Arthur Morgan cutscene no subtitles 4K",
        "God of War Kratos and Atreus cutscene no subtitles 4K",
        "The Last of Us Joel hospital cutscene no subtitles 4K",
        "GTA 5 Trevor meets Michael cutscene no subtitles 4K",
        "Cyberpunk 2077 Johnny Silverhand cutscene no subtitles 4K",
        "League of Legends cinematic with dialogue",
        "Ghost of Tsushima Jin Sakai cutscene no subtitles 4K",
        "Marvel's Spider-Man 2 official cutscene no subtitles 4K",
    ],
    "sports": [
        "Verstappen Abu Dhabi 2021 last lap team radio",
        "Lewis Hamilton iconic team radio moments",
        "F1 greatest overtakes with commentary",
        "Aguero 93:20 goal commentary Manchester City",
        "Barcelona 6-1 PSG Sergi Roberto commentary",
        "Liverpool 4-0 Barcelona corner taken quickly commentary",
        "Messi El Clasico shirt celebration commentary",
        "Champions League iconic comeback English commentary",
    ],
    "anime": [
        "Attack on Titan Eren speech scene English dub",
        "Jujutsu Kaisen Gojo throughout heaven and earth English dub",
        "Naruto vs Pain conversation scene English dub",
        "Solo Leveling Jinwoo arise scene English dub",
        "Demon Slayer Rengoku final words English dub",
        "One Piece Luffy I want to live scene English dub",
    ],
    "cartoons": [
        "Kung Fu Panda Oogway peach tree scene",
        "Kung Fu Panda Tai Lung vs Shifu scene",
        "The Lion King Mufasa Simba remember who you are scene",
        "Spider-Man Into the Spider-Verse leap of faith scene",
        "Puss in Boots The Last Wish death scene",
        "How to Train Your Dragon Hiccup Toothless scene",
    ],
}
DIALOGUE_LIGHT = {"sports", "games"}   # commentary / team radio / cutscene lines count as dialogue
NICHE_QUERIES = [q for qs in GENRES.values() for q in qs]

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
MIN_WORDS = 6          # fewer words = captionless video -> reject / shift (5 for sports / games)
MAX_LEAD = 0.9         # max seconds before the first spoken word (intro trim)
INTRO_SKIP = 15.0      # never dialogue_start < 15s on sources longer than 60s
MAX_QC_RETRIES = 2
END_CARD_S = 0.0      # end card removed (BiBi, Nov 22)
# pro-edit / Vice Cartel timeline (BiBi, Nov 23): intro montage -> dialogue in the middle -> drop -> montage.
DLG_MIN, DLG_MAX = 8.0, 18.0      # middle dialogue seconds aimed for (ends on the punch word)
DLG_HARD_MIN = 5.0                # only windows shorter than this are rejected (planner fits any 5-18s)
TOTAL_MIN, TOTAL_MAX = style.TIMELINE_MIN_S, style.TIMELINE_MAX_S
BED_GAIN = 0.28                   # ~ -11 dB under the dialogue
BED_SONGS = {"emotional_romance": ["epic_4.mp3", "epic_7.mp3"],
             "default": ["epic_5.mp3", "epic_4.mp3", "dark_6.mp3", "dark_4.mp3"]}
MAX_SONG_TRIES = 8                # songs (mood-allowed, tempo-ranked) tried until one fits the timeline


class CandidateRejected(RuntimeError):
    pass


OUTRO_S = 20.0         # clip channels end with an end screen / "subscribe" outro: never use the last 20s
OUTRO_RE = re.compile(r"^(subscribe|subscribed|subscribing|notification|notifications|patreon|channel|bell|joblo|movieclips)$")


def usable_end(dur):
    return dur - min(OUTRO_S, dur * 0.1)


def cut_outro(words):
    """Drop everything from the first outro word ('subscribe', 'channel', ...) on, plus the 3 words before it."""
    for i, w in enumerate(words):
        if OUTRO_RE.match(style.clean(w.get("word", "")).lower()):
            print(f"OUTRO speech at {w['s']:.1f}s ('{w['word']}') -> words cut there", flush=True)
            return words[: max(0, i - 3)]
    return words


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


LETTERBOX = {"crop": ""}


def detect_letterbox(src, dur, w, h):
    """Find baked-in black bars (e.g. 2.39:1 inside 16:9) so the picture fills the 4:5 width."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{min(30.0, dur / 3):.1f}", "-t", "20", "-i", str(src),
                        "-vf", "fps=2,cropdetect=limit=24:round=2:reset=0", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    crop = style.parse_cropdetect(r.stderr, w, h)
    print("LETTERBOX crop:", crop or "none", flush=True)
    return crop


def prep_cut(src, dest, start, duration, audio=True, rgb=False, preset="fast", crop=None):
    """Graded, sharpened, no-crop 4:5 cut (blurred fill top/bottom). Dialogue audio loudness-normalised.
    crop = that source's letterbox crop (extra sources have their own); every source is scaled to the same
    1080 width, graded the same way and resampled to FPS, so mixed sources look like one edit."""
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
           "-filter_complex", style.frame_filter(rgb, LETTERBOX["crop"] if crop is None else crop), "-map", "[v]",
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


def find_speech_window(src, dur, length=40.0, scan=240.0, min_words=MIN_WORDS):
    """Transcribe up to `scan` seconds after the intro and return the densest-speech window."""
    lo = min_start(dur)
    hi = min(usable_end(dur), lo + scan)
    if hi - lo < DLG_MIN:
        return None
    ws = cut_outro(whisper_words(extract_wav(src, Path("clips/scan.wav"), lo, hi - lo)))
    print("SCAN words", len(ws), f"in {lo:.0f}-{hi:.0f}s", flush=True)
    if len(ws) < min_words:
        return None
    best, best_n = None, 0
    for i, w in enumerate(ws):
        start = max(0.0, w["s"] - 1.0)
        end = start + length
        n = sum(1 for x in ws[i:] if x["e"] <= end)
        if n > best_n:
            best, best_n = (lo + start, lo + min(end, hi - lo)), n
    if best_n < min_words:
        return None
    return best


def transcribe_window(src, ds, length):
    wav = extract_wav(src, Path("clips/dialogue.wav"), ds, length)
    lang, prob = detect_language(wav)
    print(f"LANG {lang} p={prob:.2f}", flush=True)
    if lang not in ("en", "?") and prob > 0.5:
        raise CandidateRejected(f"not English ({lang} p={prob:.2f})")
    words = cut_outro(whisper_words(wav, language="en"))
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


def genre_of(query):
    if query.startswith(("url:", "channel:")):
        g = os.environ.get("GENRE", "").strip().lower()
        return g if g in GENRES else "movies"
    for g, qs in GENRES.items():
        if query in qs:
            return g
    return os.environ.get("GENRE", "movies")


class SourceRejected(CandidateRejected):
    """Rejected because of the upload itself (logo / subtitles / fan edit) -> learn the channel."""


def fetch_and_screen(url, info_hint, used_urls):
    """Download with the RapidAPI downloader, basic checks, then the cheap 5-frame Gemini pre-screen."""
    Path("clips").mkdir(exist_ok=True)
    src = Path("clips/source.mp4")
    src.unlink(missing_ok=True)
    used_urls.add(url)
    info = download_url(url, src)
    if not info:
        raise CandidateRejected("no download (RapidAPI)")
    info = {**info, **{k: v for k, v in (info_hint or {}).items() if v}}
    info.setdefault("channel", "")
    dur = probe_duration(src)
    w, h = probe_video(src)
    print("DOWNLOADED", info.get("title"), "|", info.get("channel"), f"{w}x{h}", f"{dur:.1f}s", flush=True)
    if min(w, h) < 700:
        raise CandidateRejected(f"source too low-res {w}x{h}")
    if dur < 30:
        raise CandidateRejected(f"source too short ({dur:.0f}s)")
    frames = []
    for k, frac in enumerate((0.12, 0.3, 0.5, 0.7, 0.88)):
        fp = Path(f"clips/screen_{k}.jpg")
        run(["ffmpeg", "-y", "-ss", f"{dur * frac:.2f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=768:-2", "-q:v", "4", str(fp)])
        if fp.exists():
            frames.append(fp)
    if gemini_ok() and frames:
        ps = prescreen(frames)
        print("PRESCREEN", json.dumps(ps), flush=True)
        if not ps.get("clean"):
            raise SourceRejected("pre-screen: " + str(ps.get("reason") or ps.get("flags")))
    return src, info, dur, w, h


SHOT_LIB = SL.load()


TITLE_RE = re.compile(r"\|\s*([^|]+?)\s*\((?:19|20)\d\d\)")
MAX_EXTRA = 2


def title_key(info, plan):
    """Movie / show name to find more footage of the same story (JoBlo style '| NAME (2000) Movie CLIP')."""
    m = TITLE_RE.search(info.get("title") or "")
    t = (m.group(1) if m else "") or str(plan.get("title") or "")
    return re.sub(r"\s+", " ", t).strip()


def fetch_extra_sources(info, plan, context, used_urls):
    """Yield up to MAX_EXTRA related, clean sources: (path, crop, info, gemini_shots). Same clean-source order:
    other clips of the same title on the trusted channels first, then search (official trailer / scenes).
    Every extra gets the RapidAPI download, resolution check, logo pre-screen and a Gemini shot pass."""
    key = title_key(info, plan)
    if not key:
        print("EXTRA: no title to search for", flush=True)
        return
    main_id = link_queue._vid(info.get("url", "")) if info.get("url") else ""
    got = 0
    tried = 0
    # 1) shot library: known-good sources of this title from earlier videos (already logo-screened and
    #    shot-picked -> no search / channel listing / Gemini shot pass, only the download)
    for ls in SL.sources_for(SHOT_LIB, key, exclude_ids={main_id}, exclude_urls=used_urls)[:MAX_EXTRA]:
        if got >= MAX_EXTRA or tried >= 4:
            return
        tried += 1
        used_urls.add(ls["url"])
        xpath = Path(f"clips/extra_{got + 1}.mp4")
        xpath.unlink(missing_ok=True)
        print(f"=== EXTRA SOURCE (shot library) try {tried}: {ls.get('title', '')[:80]} | {len(ls['shots'])} shots",
              flush=True)
        xi = download_url(ls["url"], xpath)
        if not xi:
            print("EXTRA (library) rejected: no download", flush=True)
            continue
        xi = {**xi, "title": ls.get("title", ""), "channel": ls.get("channel", ""), "url": ls["url"], "library": True}
        xd = probe_duration(xpath)
        xw, xh = probe_video(xpath)
        if min(xw, xh) < 700 or xd < 20:
            print(f"EXTRA (library) rejected: {xw}x{xh} {xd:.0f}s", flush=True)
            continue
        got += 1
        yield xpath, detect_letterbox(xpath, xd, xw, xh), xi, SL.as_gemini_shots(ls["shots"])
    # 2) trusted channels, then 3) search
    cands = []
    for cu in channel_source.channel_urls():
        try:
            _, vids = channel_source.list_videos(cu)
        except Exception as e:
            print("EXTRA channel listing error", repr(e)[:120], flush=True)
            continue
        same = [v for v in vids if key.lower() in v["title"].lower() and v["id"] != main_id
                and v["url"] not in used_urls and 30 <= (v["duration"] or 0) <= 900]
        cands += sorted(same, key=lambda v: -(v["views"] or 0))[:3]
    qs = [q for q in (plan.get("related_queries") or []) if isinstance(q, str)][:2] or \
         [f"{key} official trailer", f"{key} best scenes 4K"]
    for q in [None] + qs:
        if got >= MAX_EXTRA or tried >= 4:
            break
        items = cands if q is None else search_candidates(q, exclude=used_urls)[:2]
        for it in items:
            if got >= MAX_EXTRA or tried >= 4:
                break
            if it["url"] in used_urls or link_queue._vid(it["url"]) == main_id:
                continue
            tried += 1
            used_urls.add(it["url"])
            xpath = Path(f"clips/extra_{got + 1}.mp4")
            xpath.unlink(missing_ok=True)
            print(f"=== EXTRA SOURCE try {tried}: {it.get('title', '')[:80]} | {it.get('channel', '')}", flush=True)
            xi = download_url(it["url"], xpath)
            if not xi:
                print("EXTRA rejected: no download", flush=True)
                continue
            xi = {**xi, **{k: v for k, v in it.items() if v}}
            xd = probe_duration(xpath)
            xw, xh = probe_video(xpath)
            if min(xw, xh) < 700 or xd < 20:
                print(f"EXTRA rejected: {xw}x{xh} {xd:.0f}s", flush=True)
                continue
            frames = []
            for j, frac in enumerate((0.15, 0.35, 0.55, 0.75, 0.9)):
                fp = Path(f"clips/xscreen_{got + 1}_{j}.jpg")
                run(["ffmpeg", "-y", "-ss", f"{xd * frac:.2f}", "-i", str(xpath), "-frames:v", "1", "-vf", "scale=768:-2",
                     "-q:v", "4", str(fp)])
                if fp.exists():
                    frames.append(fp)
            if gemini_ok() and frames:
                ps = prescreen(frames)
                if not ps.get("clean"):
                    print("EXTRA rejected by logo pre-screen:", ps.get("reason") or ps.get("flags"), flush=True)
                    continue
            xcrop = detect_letterbox(xpath, xd, xw, xh)
            prev = Path(f"clips/extra_{got + 1}_360.mp4")
            run(["ffmpeg", "-y", "-i", str(xpath), "-t", f"{usable_end(xd):.2f}", "-vf", "scale=-2:360", "-c:v", "libx264",
                 "-preset", "ultrafast", "-crf", "30", "-an", str(prev)])
            sp = pick_shots(prev, context) if gemini_ok() else {"same_story": True, "montage_shots": []}
            if sp.get("reject") or sp.get("same_story") is False:
                print("EXTRA rejected by Gemini:", sp.get("reject_reason") or "not the same story", flush=True)
                continue
            got += 1
            print(f"EXTRA SOURCE {got} ok: {len(sp.get('montage_shots') or [])} relevant shots", flush=True)
            yield xpath, xcrop, xi, [x for x in (sp.get("montage_shots") or []) if isinstance(x, dict)]


def build_draft(src, info, dur, w, h, query, demo, cand, used_urls=None):
    """One screened source: Pass 1 -> words -> cuts -> render draft. Returns ctx dict."""
    genre = genre_of(query)
    min_words = 5 if genre in DIALOGUE_LIGHT else MIN_WORDS
    print(f"=== BUILD candidate {cand} [{genre}]: {info.get('title')} | {info.get('channel')}", flush=True)
    LETTERBOX["crop"] = detect_letterbox(src, dur, w, h)

    prev = Path("preview360.mp4")
    # preview stops before the channel outro / end screen, so Gemini never judges or picks it
    run(["ffmpeg", "-y", "-i", str(src), "-t", f"{usable_end(dur):.2f}", "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", str(prev)])

    print("[2] Gemini Pass 1 (director)", flush=True)
    plan = analyze(prev, genre) if gemini_ok() else {"dialogue_start": 15, "dialogue_end": 50, "action_cuts": [], "mood": "dark_hype"}
    if plan.get("reject"):
        why = "Gemini Pass 1 rejected: " + str(plan.get("reject_reason") or "unspecified")
        raise (SourceRejected if channel_blocklist.LEARN.search(why) else CandidateRejected)(why)
    if str(plan.get("language") or "en").lower()[:2] != "en":
        raise CandidateRejected(f"Gemini says language={plan.get('language')}")
    lo = min_start(dur)

    # ---- dialogue window (phase 1) ----
    ue = usable_end(dur)
    ds = max(lo, _num(plan.get("dialogue_start"), lo))
    bad_plan = ds > ue - DLG_MIN or _num(plan.get("dialogue_end"), 0) > dur
    if bad_plan:  # Gemini timestamps beyond the clip (or inside the outro): find the scene by speech instead
        print(f"Gemini window {plan.get('dialogue_start')}-{plan.get('dialogue_end')}s is outside the usable "
              f"0-{ue:.0f}s -> speech scan", flush=True)
        win = find_speech_window(src, dur, length=DLG_MAX + 1, scan=min(ue - lo, 420.0), min_words=min_words)
        if not win:
            raise CandidateRejected("Gemini window out of range and no speech segment found")
        ds, de = win
        plan["punch_time"] = None
    de = min(ue, _num(plan.get("dialogue_end"), ds + 40)) if not bad_plan else min(ue, de)
    punch_abs = plan.get("punch_time")
    punch_abs = _num(punch_abs, de - 1) if punch_abs not in (None, "") else None
    if punch_abs is not None and ds < punch_abs < ue:
        de = max(de, punch_abs + 1.0)
    if de - ds < DLG_MIN + 1:
        ds = max(lo, de - (DLG_MIN + 3))
    if de - ds > DLG_MAX + 2:
        ds = de - (DLG_MAX + 1)
    if de - ds < DLG_HARD_MIN:
        raise CandidateRejected(f"dialogue window too short {ds:.1f}-{de:.1f}")
    win_len = min(ue - ds, de - ds + 1.5)
    words, lang = transcribe_window(src, ds, win_len)
    if len(words) < min_words:
        print("too few words -> shifting to highest-speech segment", flush=True)
        win = find_speech_window(src, dur, length=DLG_MAX + 1, min_words=min_words)
        if not win:
            raise CandidateRejected(f"no speech segment with >= {min_words} words")
        ds, de = win
        punch_abs = None
        win_len = de - ds
        words, lang = transcribe_window(src, ds, win_len)
        if len(words) < min_words:
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

    def shift_words(sh):
        nonlocal ds, words, pidx, punch_s, punch_e
        ds += sh
        pw = words[pidx]
        words = [{**x, "s": x["s"] - sh, "e": x["e"] - sh} for x in words if x["s"] - sh >= 0.0]
        pidx = next((i for i, x in enumerate(words) if abs(x["s"] - (pw["s"] - sh)) < 1e-6), len(words) - 1)
        punch_s, punch_e = words[pidx]["s"], words[pidx]["e"]

    if punch_e + 0.1 > DLG_MAX:
        shift_words(punch_e + 0.1 - DLG_MAX)
    # intro trim: first spoken word within ~1s (no silent / dead lead-in)
    if words and words[0]["s"] > MAX_LEAD:
        shift_words(words[0]["s"] - 0.5)
    # the phase-1 words end at the punch word: the character goes quiet -> montage
    words = words[: pidx + 1]
    print(f"PUNCH '{words[pidx]['word']}' at {punch_s:.2f}-{punch_e:.2f}s (window start {ds:.2f}, "
          f"first word {words[0]['s']:.2f}s)", flush=True)

    # ---- pro-edit timeline: intro montage -> dialogue (music ducked) -> drop on the punch word -> montage ----
    mood = plan.get("mood") or "dark_hype"
    # song by mood (idea 3): scene mood (comedy / dark / epic / emotional / hype) + cached BPM tags
    smood = SM.scene_mood(plan)
    catalog = SM.load_catalog()
    cat_mood = {x.get("file"): x.get("mood") for x in catalog}
    tags = SM.load_tags()
    pool = SM.rank_songs(smood, catalog, tags)[:MAX_SONG_TRIES]
    print(f"SONG POOL scene_mood={smood}:", pool, flush=True)
    song = song_name = tl = None
    snap = (ds, list(words), pidx, punch_s, punch_e)
    for f in pool:
        got = download_bank_song(f, Path("clips/song.mp3"))
        if not got:
            continue
        ds, words, pidx, punch_s, punch_e = snap[0], list(snap[1]), snap[2], snap[3], snap[4]
        beats = detect_beats(got)
        if not (tags.get(f) or {}).get("bpm"):      # tag once, cached in config/song_tags.json (committed back)
            tags[f] = SM.tag_entry(cat_mood.get(f) or "", _num(beats.get("tempo"), 0), None, beats.get("drop"))
            SM.save_tags(tags)
        if SM.tempo_fit(tags[f].get("bpm") or 0, smood) > 30:
            print("SONG", f, "tempo", tags[f].get("bpm"), f"off for {smood} -> next", flush=True)
            continue
        bl = sorted(b for b in (beats.get("beats") or []) if isinstance(b, (int, float)))
        if len(bl) < 16:
            iv = 60.0 / max(60.0, _num(beats.get("tempo"), 120))
            bl = [k * iv for k in range(int(probe_duration(got) / iv))]
        ibi = style.median_ibi(bl)
        # nudge the lead-in so the punch word sits a whole number of beats after the dialogue cut
        # (then the cut into the dialogue, the drop and every montage cut are all on the beat)
        r = punch_s % ibi
        if r > 0.02 and words[0]["s"] - r >= 0.12:
            shift_words(r)
        elif r > 0.02 and words[0]["s"] + (ibi - r) <= MAX_LEAD + 0.4 and ds - (ibi - r) >= 0:
            shift_words(-(ibi - r))
        dlg_len = punch_e + 0.06
        try:
            tl = style.plan_timeline(bl, _num(beats.get("drop"), 0.0), probe_duration(got), dlg_len, punch_s)
        except ValueError as e:
            print("SONG", f, "does not fit:", e, flush=True)
            continue
        song, song_name = got, f
        break
    if not tl:
        raise CandidateRejected(f"no {smood} song fits the timeline (dialogue {punch_e:.1f}s)")
    print("TIMELINE", json.dumps({k: v for k, v in tl.items() if not k.endswith("_cuts")}),
          f"intro {len(tl['intro_cuts'])} cuts, outro {len(tl['outro_cuts'])} cuts, song {song_name}", flush=True)

    # global frame grid: every boundary is quantised once so the drop stays exactly on the punch word
    bounds, acc = [0.0], 0.0
    for c, _ in tl["intro_cuts"]:
        acc += c
        bounds.append(acc)
    bounds[-1] = tl["dialogue_start_s"]
    bounds.append(tl["dialogue_end_s"])
    acc = tl["dialogue_end_s"]
    for c, _ in tl["outro_cuts"]:
        acc += c
        bounds.append(acc)
    fb = [int(round(x * FPS)) for x in bounds]
    n_in = len(tl["intro_cuts"])
    intro_lens = [fb[i + 1] - fb[i] for i in range(n_in)]
    intro_frames_total = fb[n_in]
    dialogue_frames = fb[n_in + 1] - fb[n_in]
    outro_lens = [fb[i + 1] - fb[i] for i in range(n_in + 1, len(fb) - 1)]
    kinds = [k for _, k in tl["intro_cuts"]] + [k for _, k in tl["outro_cuts"]]
    D = dialogue_frames / FPS
    drop_frame = intro_frames_total + int(round(punch_s * FPS))

    print("[3] FFmpeg graded cuts", flush=True)
    dlg = Path("clips/dialogue.mp4")
    prep_cut(src, dlg, ds, D + 0.3, audio=True, preset="medium")
    if int(math.floor(probe_duration(dlg) * FPS)) < dialogue_frames:
        raise CandidateRejected("dialogue cut shorter than planned")

    # ---- montage shots: inventory of distinct camera shots, Gemini relevance, no repeats, multi-source ----
    need = n_in + len(outro_lens)
    intro_s = [f / FPS for f in intro_lens]
    outro_s = [f / FPS for f in outro_lens]
    used_urls = used_urls if used_urls is not None else set()
    sources = {"main": (src, LETTERBOX["crop"])}
    src_ids = {"main": (link_queue._vid(info.get("url", "")) if info.get("url") else "", info)}
    chunks = msel.inventory(src, "main", lo, ue, crop=LETTERBOX["crop"], blocked=[(ds, ds + D)])
    gshots = [x for x in (plan.get("montage_shots") or []) if isinstance(x, dict)]
    if msel.lazy_times([x.get("t") for x in gshots]):
        print("Gemini montage_shots look evenly spaced (not real picks) -> ignored", flush=True)
        gshots = []
    if not gshots and not msel.lazy_times(plan.get("action_cuts") or []):
        gshots = [{"t": t, "energy": 5, "kind": "action", "reason": "director action cut"}
                  for t in plan.get("action_cuts") or [] if isinstance(t, (int, float))]
    msel.apply_gemini(chunks, gshots, "main")
    main_id = link_queue._vid(info.get("url", "")) if info.get("url") else ""
    lib_main = [x for x in SL.sources_for(SHOT_LIB, title_key(info, plan)) if x["id"] == main_id]
    if lib_main:   # this source was used before: its saved good shots count too
        print(f"SHOT LIBRARY: {msel.apply_gemini(chunks, SL.as_gemini_shots(lib_main[0]['shots']), 'main')} "
              "main chunks boosted from earlier picks", flush=True)
    min_len = min(intro_s + outro_s)
    pool = msel.unique_pool(chunks, min_len)
    strong = [c for c in pool if c.energy >= 5 or c.motion >= 12 or c.loud >= 7]
    print(f"MONTAGE main: {len(chunks)} chunks, {len(pool)} unique looks, {len(strong)} strong, need {need}; "
          f"director says sufficient={plan.get('montage_sufficient')}", flush=True)
    extras_used = []
    if len(pool) < need or len(strong) < int(0.6 * need) or plan.get("montage_sufficient") is False:
        context = {"title": plan.get("title") or info.get("title", ""), "scene": plan.get("scene", ""),
                   "characters": plan.get("characters") or [], "dialogue": " ".join(w["word"] for w in words),
                   "mood": mood, "hook": plan.get("hook_title", "")}
        for k, (xpath, xcrop, xinfo, xshots) in enumerate(fetch_extra_sources(info, plan, context, used_urls)):
            sid = f"x{k + 1}"
            xd = probe_duration(xpath)
            xc = msel.inventory(xpath, sid, min(3.0, xd * 0.05), usable_end(xd), crop=xcrop)
            msel.apply_gemini(xc, xshots, sid)
            # an extra source only contributes the shots Gemini judged relevant (or clearly moving)
            xc = [c for c in xc if c.energy >= 4 or c.motion >= 14 or c.loud >= 7]
            chunks += xc
            sources[sid] = (xpath, xcrop)
            src_ids[sid] = (link_queue._vid(xinfo.get("url", "")), xinfo)
            extras_used.append({"id": sid, "title": xinfo.get("title", ""), "channel": xinfo.get("channel", ""),
                                "url": xinfo.get("url", ""), "chunks": len(xc)})
            pool = msel.unique_pool(chunks, min_len)
            strong = [c for c in pool if c.energy >= 5 or c.motion >= 12 or c.loud >= 7]
            print(f"MONTAGE +{sid}: {len(xc)} relevant chunks -> {len(pool)} unique, {len(strong)} strong", flush=True)
            if len(pool) >= need and len(strong) >= int(0.6 * need):
                break
    try:
        picks = msel.select(chunks, intro_s, outro_s)
    except msel.NotEnough as e:
        raise CandidateRejected(f"not enough distinct montage shots ({e}) even with {len(extras_used)} extra source(s)")
    bad = msel.audit(picks)
    if bad:
        raise CandidateRejected("montage audit: " + "; ".join(bad[:3]))
    print("MONTAGE picks:", json.dumps([{k: p[k] for k in ("src", "start", "dur", "role", "energy", "loud", "kind", "hit")}
                                        for p in picks]), flush=True)
    # shot library (idea 5): save the good shots of every source used, keyed by title (committed back)
    lib_title = title_key(info, plan)
    for sid, (vid, sinfo) in src_ids.items():
        n_saved = SL.add(SHOT_LIB, lib_title, vid, sinfo, [c for c in chunks if c.src == sid])
        if n_saved:
            print(f"SHOT LIBRARY '{SL.key(lib_title)}' {vid}: {n_saved} shots saved", flush=True)
    SL.save(SHOT_LIB)
    lens = intro_lens + outro_lens
    paths = []
    for i, (pk, want) in enumerate(zip(picks, lens)):
        ap = Path(f"clips/action_{i}.mp4")
        xpath, xcrop = sources[pk["src"]]
        # light colour split only on the hit cuts (drop + hero shots), like ref1/ref2
        prep_cut(xpath, ap, pk["start"], want / FPS + 0.15, audio=False, rgb=bool(pk.get("hit")), crop=xcrop)
        if not ap.exists() or int(math.floor(probe_duration(ap) * FPS)) < want:
            raise CandidateRejected(f"montage cut {i} too short at {pk['src']}@{pk['start']:.1f}s")
        paths.append(ap)
    if len(paths) != need or need < 12:
        raise CandidateRejected(f"only {len(paths)}/{need} montage cuts")

    total = intro_frames_total + dialogue_frames + sum(outro_lens)
    if not (TOTAL_MIN * FPS <= total <= 60 * FPS):
        raise CandidateRejected(f"length {total / FPS:.1f}s outside 35-60s")

    # ---- picture rect inside the 4:5 frame (for watermark + caption band) ----
    cw, ch = (w, h)
    if LETTERBOX["crop"]:
        cw, ch = (int(v) for v in LETTERBOX["crop"].split(":")[:2])
    sc = min(style.W / cw, style.H / ch)
    pw, ph = cw * sc, ch * sc
    pic = {"x": round((style.W - pw) / 2), "y": round((style.H - ph) / 2), "w": round(pw), "h": round(ph)}
    banner_h = int(style.H * 0.10)
    band = (max(pic["y"], banner_h + 8) + 6, pic["y"] + pic["h"] - 6)

    # ---- captions: speaker-side styles (pro-edit P01-P15 + R00 glow), word-level timing ----
    cap_style = captions_mod.pick_style(mood, info.get("url", "") + query)
    groups = style.group_captions(words, pidx, dialogue_frames / FPS, max_words=min(4, cap_style["words"] + 1))
    groups = [{"start": g["start"], "end": g["end"], "words": g["raw"]} for g in groups]
    cap_events, cap_info = captions_mod.build_events(groups, pidx, cap_style, dlg, style.W, style.H, band, FPS)
    print("CAPTIONS style", cap_style["id"], cap_style["name"], "|", len(cap_events), "events", cap_info, flush=True)
    hook = (plan.get("hook_title") or plan.get("hook") or "").strip().strip('"')
    if not style.good_hook(hook):
        hook = " ".join((plan.get("scene") or info.get("title") or "The Moment").split()[:3])
    # no opening question / hook caption any more (BiBi, Nov 24): stripped from the plan, never rendered
    style.strip_intro_question(plan)
    plan.update({"hook_title": hook})
    if not plan.get("post_caption"):
        plan["post_caption"] = f"Clip: {info.get('title','')} | Credit: {info.get('channel','')} | Edited under Fair Use."

    assets_dir = Path("remotion/public/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    for f in assets_dir.glob("*"):
        f.unlink(missing_ok=True)
    shutil.copy(dlg, assets_dir / "dialogue.mp4")
    rel = []
    for i, ap in enumerate(paths):
        shutil.copy(ap, assets_dir / f"action_{i}.mp4")
        rel.append(f"assets/action_{i}.mp4")
    # one song through the whole video (pro-edit): starts at song_start so its drop beat lands on the punch word;
    # ducked to BED_GAIN (~-11 dB) under the dialogue in Remotion, full level in both montages
    run(["ffmpeg", "-y", "-ss", f"{tl['song_start']:.3f}", "-t", f"{total / FPS + 0.5:.3f}", "-i", str(song),
         "-map", "0:a:0", "-vn", "-af", "loudnorm=I=-11:TP=-1.0:LRA=9,afade=t=in:d=0.05", "-ar", "48000", "-ac", "2",
         "-c:a", "aac", "-b:a", "256k", str(assets_dir / "music.m4a")])
    make_sfx(assets_dir)
    wm_size = captions_mod.watermark_size("RIYIO", style.W, style.WM_FRAC)
    # hit SFX on the strongest cuts (drop + hero shots), whoosh just before each hero cut (self-made SFX)
    cut_starts = [sum(intro_lens[:i]) for i in range(n_in)] + \
        [intro_frames_total + dialogue_frames + sum(outro_lens[:j]) for j in range(len(outro_lens))]
    hit_frames = sorted({drop_frame} | {cut_starts[i] for i, pk in enumerate(picks) if pk.get("hit") and i > n_in})  # slot n_in = drop
    whoosh_frames = [max(0, f - 6) for f in hit_frames if f != drop_frame]

    props = {
        "hook": hook,
        "introClips": rel[:n_in],
        "introFrames": intro_lens,
        "dialogueSrc": "assets/dialogue.mp4",
        "dialogueFrom": intro_frames_total,
        "dialogueFrames": dialogue_frames,
        "dropFrame": drop_frame,
        "actionClips": rel[n_in:],
        "actionFrames": outro_lens,
        "actionKinds": kinds[n_in:],
        "musicSrc": "assets/music.m4a",
        "captions": cap_events,
        "captionFont": cap_style["font"],
        "captionLook": cap_style["look"],
        "bedSrc": "",
        "bedVolume": BED_GAIN,
        "dropSrc": "",
        "hitSrc": "assets/hit.wav",
        "whooshSrc": "assets/whoosh.wav",
        "hitFrames": hit_frames,
        "whooshFrames": whoosh_frames,
        "wmOpacity": style.WM_OPACITY,
        "picture": pic,
        "wmSize": wm_size,
        "durationInFrames": total,
        "post_caption": plan.get("post_caption", ""),
    }
    Path("remotion-props.json").write_text(json.dumps(props, indent=2))
    meta = {**plan, "genre": genre_of(query), "query": query, "source": info, "source_res": f"{w}x{h}",
            "letterbox_crop": LETTERBOX["crop"], "picture": pic, "window_start": round(ds, 2),
            "first_word_s": round(intro_frames_total / FPS + words[0]["s"], 2), "punch": words[pidx]["word"],
            "punch_s": round(intro_frames_total / FPS + punch_s, 3), "drop_s": round(drop_frame / FPS, 3),
            "structure": "intro montage -> dialogue (ducked music, captions) -> drop on punch word -> montage",
            "intro_s": round(intro_frames_total / FPS, 2), "intro_cuts": n_in,
            "dialogue_start_s": round(intro_frames_total / FPS, 2),
            "montage_start_s": round((intro_frames_total + dialogue_frames) / FPS, 3),
            "montage_sources": 1 + len(extras_used), "extra_sources": extras_used,
            "montage_picks": [{k: p[k] for k in ("src", "start", "dur", "role", "energy", "loud", "motion", "kind", "hit",
                                                 "reason")} for p in picks],
            "montage_repeats": len(msel.audit(picks)),
            "scene_mood": smood, "song_mood": cat_mood.get(song_name), "song_bpm": (tags.get(song_name) or {}).get("bpm"),
            "hit_cuts": len(hit_frames), "intro_caption": "none", "fps_out": 60,
            "song": song_name, "song_start_s": tl["song_start"], "song_drop_beat_s": tl["song_drop_beat"],
            "beat_s": tl["ibi"], "words": len(words), "language": lang,
            "dialogue_s": round(dialogue_frames / FPS, 2), "montage_s": round(sum(outro_lens) / FPS, 2),
            "montage_cuts": len(outro_lens), "total_s": round(total / FPS, 2), "captions": len(cap_events),
            "caption_style": f"{cap_style['id']} {cap_style['name']}", "caption_zones": cap_info}
    Path("plan.json").write_text(json.dumps(meta, indent=2, default=str))
    print("PLAN", json.dumps({k: meta[k] for k in ("genre", "scene", "punch", "punch_s", "drop_s", "intro_s",
                                                  "dialogue_start_s", "montage_start_s", "first_word_s", "song",
                                                  "dialogue_s", "montage_s",
                                                  "montage_cuts", "total_s", "words", "captions", "caption_style",
                                                  "hook_title", "scene_mood", "song_bpm", "hit_cuts")}, default=str), flush=True)

    print("[5] Remotion render (draft)", flush=True)
    draft = Path("out_remotion.mp4")
    draft.unlink(missing_ok=True)
    flags = "--props=../remotion-props.json --jpeg-quality=95 --crf=16 --x264-preset=medium --audio-bitrate=192k"
    run(["bash", "-c", f"cd remotion && ./node_modules/.bin/remotion render src/index.ts JuraijEdit ../out_remotion.mp4 {flags} || npx --no-install remotion render src/index.ts JuraijEdit ../out_remotion.mp4 {flags}"])
    if not draft.exists() or draft.stat().st_size < 1000:
        raise RuntimeError("Remotion produced no output")
    print("REMOTION OK", draft.stat().st_size, "dur", probe_duration(draft), "expected", round(total / FPS, 2), flush=True)
    return {"draft": draft, "props": props, "plan": meta, "info": info}


GENRE_FALLBACK = ["movies", "web_series", "cartoons", "anime", "games", "sports"]
MAX_DOWNLOADS = 12        # sources downloaded + screened per run before giving up
PER_QUERY = 3             # results tried per search query
MAX_QUERIES = 14          # search calls per run (RapidAPI quota)
REJECTS: list[dict] = []


def genre_order():
    forced = os.environ.get("GENRE", "").strip().lower()
    start = forced if forced in GENRES else \
        list(GENRES)[int(os.environ.get("GITHUB_RUN_NUMBER") or random.randint(0, 99)) % len(GENRES)]
    return [start] + [g for g in GENRE_FALLBACK if g != start]


def search_terms(q):
    """Steer search toward clean uploads (no burned-in subs / logos)."""
    g = genre_of(q)
    if g == "sports":
        return q + " official"
    if g == "games" or "no subtitles" in q:
        return q
    if g == "anime":
        return q + " no subtitles"
    return q + (" 4K clean no subtitles" if "scene" in q else " scene 4K clean no subtitles")


def query_plan(tried):
    """Queries alternating across genres (never more than one query in a row per genre)."""
    env_q = os.environ.get("QUERY")
    out = [env_q] if env_q and env_q not in tried else []
    pools = {g: [q for q in random.sample(GENRES[g], len(GENRES[g])) if q not in tried] for g in genre_order()}
    while any(pools.values()):
        for g in genre_order():
            if pools[g]:
                out.append(pools[g].pop(0))
    return out


def _attempt(url, hint, query, used_urls, demo, n, link=False, track=None):
    try:
        src, info, dur, w, h = fetch_and_screen(url, hint, used_urls)
        ctx = build_draft(src, info, dur, w, h, query, demo, n, used_urls)
        Path("rejects.json").write_text(json.dumps(REJECTS, indent=2))
        if link or track:
            link_queue.mark(url, track or "used", info.get("title", ""))
        return ctx
    except CandidateRejected as e:
        ch = (hint or {}).get("channel") or ""
        if isinstance(e, SourceRejected) and not track:  # trusted channels: learned after 2 rejects (below)
            channel_blocklist.learn(ch, str(e), (hint or {}).get("title", ""))
        REJECTS.append({"n": n, "query": query, "title": (hint or {}).get("title", "") or url, "channel": ch,
                        "reason": str(e)[:200]})
        print("CANDIDATE REJECTED:", e, flush=True)
        if link or track:
            link_queue.mark(url, "rejected", str(e))
    except Exception as e:  # one bad source/tool step must not kill the whole run
        REJECTS.append({"n": n, "query": query, "title": (hint or {}).get("title", "") or url, "reason": "error: " + repr(e)[:180]})
        traceback.print_exc()
        print("CANDIDATE FAILED (trying next):", repr(e)[:300], flush=True)
        if link or track:
            link_queue.mark(url, "rejected", "error: " + repr(e)[:150])
    return None


def build_with_candidates(tried, used_urls, demo):
    # 1) workflow_dispatch source_url overrides everything (no fallback)
    src_url = os.environ.get("SOURCE_URL", "").strip()
    if src_url and src_url in used_urls:
        raise RuntimeError("source_url clip did not pass QC; send another link")
    if src_url:
        ctx = _attempt(src_url, {}, f"url:{src_url}", used_urls, demo, 1)
        if ctx:
            return ctx
        raise RuntimeError(f"source_url rejected: {REJECTS[-1]['reason'] if REJECTS else 'unknown'}")
    n = 0
    # 2) links/queue.txt first (each link once; used / rejected logged in links/used.txt)
    for url in link_queue.pending():
        if url in used_urls:
            continue
        n += 1
        print(f"=== LINK {n}: {url}", flush=True)
        ctx = _attempt(url, {}, f"url:{url}", used_urls, demo, n, link=True)
        if ctx:
            return ctx
    # 3) trusted channels (channels/channels.txt): recent/popular scene clips, still pre-screened
    skip_ids = link_queue.used_ids() | {link_queue._vid(u) for u in used_urls}
    ch_rejects = {}
    for v in channel_source.candidates(skip_ids):
        if ch_rejects.get(v["channel"], 0) >= 2 or channel_blocklist.is_blocked(v["channel"]):
            continue
        n += 1
        print(f"=== CHANNEL VIDEO {n}: {v['title'][:80]} | {v['channel']}", flush=True)
        before = len(REJECTS)
        ctx = _attempt(v["url"], v, f"channel:{v['channel']}", used_urls, demo, n, track="channel-used")
        if ctx:
            return ctx
        if len(REJECTS) > before and channel_blocklist.LEARN.search(REJECTS[-1]["reason"]):
            ch_rejects[v["channel"]] = ch_rejects.get(v["channel"], 0) + 1
            if ch_rejects[v["channel"]] >= 2:
                channel_blocklist.learn(v["channel"], REJECTS[-1]["reason"], v["title"])
    # 4) auto search across genres with ranked, pre-filtered results
    downloads = 0
    for qi, q in enumerate(query_plan(tried)):
        if qi >= MAX_QUERIES:
            break
        tried.add(q)
        print(f"=== QUERY [{genre_of(q)}]: {q}", flush=True)
        for it in search_candidates(search_terms(q), exclude=used_urls)[:PER_QUERY]:
            if downloads >= MAX_DOWNLOADS:
                break
            downloads += 1
            n += 1
            ctx = _attempt(it["url"], it, q, used_urls, demo, n)
            if ctx:
                return ctx
        if downloads >= MAX_DOWNLOADS:
            break
    Path("rejects.json").write_text(json.dumps(REJECTS, indent=2))
    raise RuntimeError(f"no usable candidate after {downloads} downloads; rejects in rejects.json")


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


def silent_segments(video):
    """Local check: music must be audible the whole video (no gaps below -45 dB for 0.4s+)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "silencedetect=noise=-45dB:d=0.4",
                        "-vn", "-f", "null", "-"], capture_output=True, text=True)
    return [ln.split("]")[-1].strip() for ln in r.stderr.splitlines() if "silence_start" in ln]


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
        blacks = black_segments(draft, dlen)
        silences = silent_segments(draft)
        pl = ctx["plan"]
        facts = {"duration_s": round(dlen, 2), "genre": pl.get("genre"), "language": pl.get("language"),
                 "whisper_words": pl.get("words"), "caption_groups": pl.get("captions"),
                 "caption_style": pl.get("caption_style"), "first_word_s": pl.get("first_word_s"),
                 "punch_word": pl.get("punch"), "punch_word_s": pl.get("punch_s"), "drop_s": pl.get("drop_s"),
                 "intro_montage_s": pl.get("intro_s"), "dialogue_start_s": pl.get("dialogue_start_s"),
                 "montage_start_s": pl.get("montage_start_s"), "montage_cuts": pl.get("montage_cuts"),
                 "dialogue_s": pl.get("dialogue_s"), "montage_s": pl.get("montage_s"), "end_card": "none",
                 "montage_unique_shots": len(pl.get("montage_picks") or []), "montage_sources": pl.get("montage_sources"),
                 "montage_repeats_found": pl.get("montage_repeats"),
                 "watermark": f"small faint glass RIYIO ({style.WM_OPACITY:.0%} opacity) inside the picture, bottom-center",
                 "intro_caption": "none (no opening question caption)", "scene_mood": pl.get("scene_mood"),
                 "song_mood": pl.get("song_mood"), "hit_cuts": pl.get("hit_cuts"), "black_segments": blacks,
                 "silent_segments": silences}
        print("QC FACTS", json.dumps(facts), flush=True)
        qc360 = Path("draft360.mp4")
        run(["ffmpeg", "-y", "-i", str(draft), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", str(qc360)])
        verdict = qc_inspect(qc360, facts)
        local = []
        if not (TOTAL_MIN <= dlen <= 60.0):
            local.append(f"length {dlen:.1f}s outside 35-60s")
        if blacks:
            local.append(f"black frames: {blacks[:3]}")
        if silences:
            local.append(f"music not audible: {silences[:3]}")
        if pl.get("montage_repeats"):
            local.append(f"montage repeats {pl.get('montage_repeats')} shot(s)")
        if abs(_num(pl.get("drop_s"), 0) - _num(pl.get("punch_s"), -9)) > 0.05:
            local.append("drop not on the punch word")
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
    print("[7] 60 fps smoothing + 4K upscale 2160x2700", flush=True)
    final = Path("out.final.mp4")
    upscale_hdr(draft, final, preset="medium", fps60=True)   # 60 fps smoothing, then 4K
    print("FINAL", final.stat().st_size, "dur", probe_duration(final), flush=True)
    buffer_post("", ctx["props"]["post_caption"], demo)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
