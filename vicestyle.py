#!/usr/bin/env python3
"""vicestyle — 4K dual-render fan-edit engine with RIYIO branding.

Modes:
  python vicestyle.py auto   --song S --clips DIR --out OUT.mp4 [--mode dual|wide|shorts]
  python vicestyle.py render --song S --plan PLAN.json --out OUT.mp4

Default: dual 4K (16:9 YouTube/X + 9:16 Instagram), 38s, RIYIO watermark,
uniform 21:9 letterbox, sleek captions from caption_patterns.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageChops

import caption_patterns as CP

FPS = 30
HOLD_EXTRA_S = 1.5
WM_HEIGHT = 0.034
WM_BOTTOM = 0.12
WM_PAD = 18
WM_BLUR = 8
WM_BRIGHTNESS = 1.15
WM_TINT_ALPHA = 22
WM_SHADOW = 0.12
WM_GLASS_MASK = 0.60
WM_EDGE = 0.38
GRADE = "eq=contrast=1.12:saturation=1.28:brightness=0.01:gamma=0.98"
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass
class Seg:
    kind: str          # montage | dialogue
    src: str
    start: float
    beats: int
    zoom: float = 1.0
    sfx: float = 0.0
    name: str = ""
    t0: float = 0.0
    t1: float = 0.0
    f0: int = 0
    f1: int = 0
    gamma: float | None = None


def run(cmd, timeout=600, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd[:6])} ...\n{(r.stderr or '')[-800:]}")
    return r


def probe_duration(path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip() or 0)


def cache_dir() -> Path:
    d = Path.home() / ".cache" / "riyio-edits"
    d.mkdir(parents=True, exist_ok=True)
    return d


def detect_beats(song: Path) -> dict:
    """Simple tempo + beat grid. Falls back to fixed BPM if librosa missing."""
    try:
        import librosa
        y, sr = librosa.load(str(song), sr=22050, mono=True)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        tempo = float(np.atleast_1d(tempo)[0])
        beats = [float(b) for b in beats]
        if len(beats) < 4:
            raise ValueError("too few beats")
    except Exception:
        tempo = 120.0
        dur = probe_duration(song) or 60.0
        beats = [i * 60.0 / tempo for i in range(int(dur * tempo / 60) + 2)]
    period = 60.0 / max(tempo, 60.0)
    return {"tempo": tempo, "period": period, "beats": beats}


def pick_song_start(binfo: dict, needed_beats: int) -> float:
    beats = binfo["beats"]
    if len(beats) <= needed_beats + 2:
        return beats[0] if beats else 0.0
    best, best_score = beats[0], -1
    for i in range(0, len(beats) - needed_beats, 4):
        score = sum(1 for j in range(i, i + needed_beats) if j < len(beats))
        if score > best_score:
            best_score, best = score, beats[i]
    return best


def hold_beats(period: float, base: int = 1, extra_s: float = HOLD_EXTRA_S) -> int:
    return max(1, int(round((base * period + extra_s) / period)))


# ---------- filter / cut ----------
def seg_filter(seg: Seg, W: int, H: int) -> str:
    z = max(1.0, seg.zoom)
    f = [f"scale={int(W * z)}:{int(H * z)}:force_original_aspect_ratio=increase:flags=lanczos",
         f"crop={W}:{H}", "setsar=1", GRADE]
    # Immersive crop (no thin letterbox strip). Slight punch on montage.
    if seg.kind == "montage":
        f.append("eq=contrast=1.15:saturation=1.22:brightness=0.02")
        f.append("unsharp=5:5:0.6:5:5:0.0")
    else:
        f.append("vignette=angle=PI/5")
    f.append("noise=alls=3:allf=t")
    f.append(f"fps={FPS},format=yuv420p")
    return ",".join(f)


def cut_segment(seg: Seg, W: int, H: int, tmp: Path) -> Path:
    nfr = max(1, seg.f1 - seg.f0)
    out = tmp / f"seg_{id(seg)}.mp4"
    pre = max(0.0, seg.start - 1.5)
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{pre:.3f}", "-i", seg.src,
           "-ss", f"{seg.start - pre:.3f}", "-vf", seg_filter(seg, W, H),
           "-frames:v", str(nfr), "-an", "-c:v", "libx264", "-preset", "fast",
           "-crf", "16", "-pix_fmt", "yuv420p", str(out)]
    run(cmd)
    return out


# ---------- captions ----------
def chunk_words(words: list[dict], max_words: int = 3) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["s"] - cur[-1]["e"] > 0.3):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def clean_word(w: str) -> str:
    return re.sub(r"[^A-Za-z0-9'?!]", "", w).upper()


def render_caption_block(items: list[tuple], fpath: str, anim: str = "pop") -> Image.Image:
    """Strong multi-color glowing captions (Money Really Talks style)."""
    lines = []
    for t, c, s in items:
        f = ImageFont.truetype(fpath, int(s * 1.15))
        bb = f.getbbox(t)
        lines.append((t, c, int(s * 1.15), f, bb))
    pad = 40
    gap = 6
    Wb = max((bb[2] - bb[0] for *_, bb in lines), default=140) + pad * 2
    Hb = sum((bb[3] - bb[1] for *_, bb in lines)) + gap * max(0, len(lines) - 1) + pad * 2
    img = Image.new("RGBA", (Wb, Hb), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (Wb, Hb), (0, 0, 0, 0))
    glow = Image.new("RGBA", (Wb, Hb), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ds = ImageDraw.Draw(shadow)
    dg = ImageDraw.Draw(glow)
    y = pad
    for t, c, s, f, bb in lines:
        x = (Wb - (bb[2] - bb[0])) // 2 - bb[0]
        # heavy neon glow
        for r, a in ((4, 90), (8, 60), (14, 40)):
            dg.text((x, y - bb[1]), t, font=f, fill=(*c, a), stroke_width=r)
        ds.text((x + 2, y + 3 - bb[1]), t, font=f, fill=(0, 0, 0, 220))
        d.text((x, y - bb[1]), t, font=f, fill=(*c, 255),
               stroke_width=max(2, s // 20), stroke_fill=(0, 0, 0, 255))
        y += (bb[3] - bb[1]) + gap
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    out = Image.alpha_composite(glow, shadow)
    out = Image.alpha_composite(out, img)
    return out


def _words_for(src: str, whisper_words) -> list[dict]:
    if not whisper_words:
        return []
    if isinstance(whisper_words, dict):
        for k, v in whisper_words.items():
            if Path(k).name == Path(src).name:
                return v or []
        return []
    return whisper_words  # legacy single-clip list


def build_captions(segs: list[Seg], W: int, H: int, pattern: dict, base: Path,
                   whisper_words=None) -> list[dict]:
    """Beside-speaker captions from real Whisper word timings, mapped onto the
    EDIT timeline: every word spoken inside every dialogue segment is captioned
    (full dialogue, not just the first few words).
    whisper_words: {clip_path: [{"word","s","e"}]} or legacy list.
    """
    events = []
    fpath = CP.font_path(pattern.get("font_hint"))
    for seg in segs:
        if seg.kind != "dialogue":
            continue
        span = seg.t1 - seg.t0
        local = []
        for w in _words_for(seg.src, whisper_words):
            if seg.start <= w["s"] < seg.start + span - 0.05:
                d = seg.t0 - seg.start
                local.append({"word": w["word"], "s": w["s"] + d, "e": min(w["e"] + d, seg.t1)})
        for ch in chunk_words(local, max_words=3):
            s = ch[0]["s"]
            e = ch[-1]["e"]
            items = [(clean_word(w["word"]), pattern["keys"][i % len(pattern["keys"])],
                      int(H * pattern["key"] * 1.12))
                     for i, w in enumerate(ch) if clean_word(w["word"])]
            if not items:
                continue
            img = render_caption_block(items, fpath, pattern.get("anim", "pop"))
            # Cinematic lower-center / center placement (matches reference edits)
            x = max(20, (W - img.width) // 2)
            y = int(H * 0.58)
            events.append({
                "f0": int(s * FPS), "f1": int(min(max(e + 0.3, s + 0.6), s + 3.5, seg.t1) * FPS),
                "img": img, "x": x, "y": y, "text": " ".join(t for t, *_ in items),
                "anim": pattern.get("anim", "pop"), "pop": True,
            })
    events.sort(key=lambda e: e["f0"])
    for a, b in zip(events, events[1:]):  # one caption block on screen at a time
        a["f1"] = max(a["f0"] + 1, min(a["f1"], b["f0"]))
    return events


# ---------- watermark ----------
def apply_riyio_logo(im: Image.Image, fpath: str) -> Image.Image:
    """Frosted-glass RIYIO mark, bottom-center."""
    im = im.convert("RGBA")
    W, H = im.size
    text = "RIYIO"
    f = ImageFont.truetype(fpath, int(H * WM_HEIGHT))
    bb = f.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad = WM_PAD
    bw, bh = tw + 2 * pad, th + 2 * pad
    x = (W - bw) // 2
    y = H - bh - int(H * WM_BOTTOM)
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).text((pad - bb[0], pad - bb[1]), text, font=f, fill=255)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + bw), min(H, y + bh)
    if x1 <= x0 or y1 <= y0:
        return im
    mx0, my0 = x0 - x, y0 - y
    reg = im.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(WM_BLUR))
    reg = ImageEnhance.Brightness(reg).enhance(WM_BRIGHTNESS)
    tint = Image.new("RGBA", reg.size, (255, 255, 255, WM_TINT_ALPHA))
    reg = Image.alpha_composite(reg.convert("RGBA"), tint)
    use = mask.crop((mx0, my0, mx0 + reg.size[0], my0 + reg.size[1]))
    shadow = use.filter(ImageFilter.GaussianBlur(4)).point(lambda v: int(v * WM_SHADOW))
    im.paste(Image.new("RGBA", reg.size, (0, 0, 0, 255)), (x0 + 2, y0 + 3), shadow)
    im.paste(reg, (x0, y0), use.point(lambda v: int(v * WM_GLASS_MASK)))
    edge = ImageChops.subtract(use, use.filter(ImageFilter.MinFilter(3))).point(lambda v: int(v * WM_EDGE))
    im.paste(Image.new("RGBA", reg.size, (255, 255, 255, 255)), (x0, y0), edge)
    return im


# ---------- audio ----------
def load_audio(path: Path, sr: int, start: float, dur: float) -> np.ndarray:
    """Decode [start, start+dur] of any audio/video file to float32 stereo via ffmpeg.
    Raises if nothing could be decoded (no silent/dummy fallback)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}",
                        "-i", str(path), "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True, timeout=300)
    data = np.frombuffer(r.stdout, dtype=np.float32)
    if r.returncode != 0 or data.size == 0:
        raise RuntimeError(f"audio decode failed for {Path(path).name}: {r.stderr[-300:]!r}")
    return data.reshape(-1, 2).copy()


def mix_audio(song: Path, song_start: float, total: float, segs: list[Seg], out: Path,
              duck: float = 0.42, ramp: float = 0.25, tail_fade: float = 1.8,
              slowed_reverb: bool = False):
    sr = 48000
    n = int(round(total * sr))
    music = load_audio(song, sr, song_start, total)
    if len(music) < n:
        music = np.vstack([music, np.zeros((n - len(music), 2), np.float32)])
    music = music[:n]
    if slowed_reverb:
        # -6% speed/pitch + subtle hall reverb
        new_len = int(len(music) * 0.94)
        idx = np.linspace(0, len(music) - 1, new_len).astype(int)
        music = music[idx]
        if len(music) < n:
            music = np.vstack([music, np.zeros((n - len(music), 2), np.float32)])
        music = music[:n]
        delay = int(0.08 * sr)
        if len(music) > delay:
            music[delay:] += 0.18 * music[:-delay]
    env = np.ones(n, np.float32)
    voice = np.zeros((n, 2), np.float32)
    for seg in segs:
        a, b = int(seg.t0 * sr), int(seg.t1 * sr)
        if seg.kind == "dialogue":
            env[a:b] = duck
            v = load_audio(Path(seg.src), sr, seg.start, max(0.1, seg.t1 - seg.t0))
            if len(v):
                rms = np.sqrt(np.mean(v ** 2)) + 1e-9
                v = v * min(5.0, 0.38 / rms)
                voice[a:a + len(v)] += v[:n - a]
    k = int(ramp * sr)
    if k > 1:
        kern = np.ones(k, np.float32) / k
        env = np.convolve(np.pad(env, (k // 2, k - k // 2 - 1), mode="edge"), kern, mode="valid")[:n]
    mixed = music * env[:, None] + voice
    peak = np.max(np.abs(mixed)) + 1e-9
    mixed = np.tanh(mixed * (0.98 / max(peak, 0.98)) * 1.1) / np.tanh(1.1)
    ft = min(len(mixed), int(tail_fade * sr))
    if ft > 0:
        mixed[-ft:] *= np.linspace(1, 0, ft)[:, None]
    import soundfile as sf
    sf.write(str(out), mixed, sr, subtype="PCM_24")


# ---------- composite / render ----------
def composite(base: Path, events: list[dict], W: int, H: int, audio: Path, out: Path,
              nframes: int, crf: int, fpath: str):
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(base), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio),
        "-map", "0:v", "-map", "1:a",
        "-vf", "hqdn3d=1.5:1.5:6:6,unsharp=5:5:0.45:5:5:0.0",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-maxrate", "60M", "-bufsize", "120M", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", str(out)
    ], stdin=subprocess.PIPE)
    fsz = W * H * 3
    for fi in range(nframes):
        buf = dec.stdout.read(fsz)
        if len(buf) < fsz:
            buf = bytes(fsz)
        act = [e for e in events if e["f0"] <= fi < e["f1"]]
        im = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1).convert("RGBA")
        for e in act:
            img = e["img"]
            im.alpha_composite(img, (max(0, e["x"]), max(0, e["y"])))
        im = apply_riyio_logo(im, fpath)
        enc.stdin.write(im.convert("RGB").tobytes())
    enc.stdin.close()
    enc.wait()
    dec.kill()
    dec.wait()
    if enc.returncode:
        raise RuntimeError("encode failed")


def make_shorts(wide: Path, out: Path, hook: str, fpath: str):
    """Full 9:16 center-crop + top title bar."""
    probe = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(wide)], check=False)
    if "video" not in (probe.stdout or ""):
        raise RuntimeError(f"wide render has no video stream: {wide}")
    title = (hook or "MONEY REALLY TALKS").upper()[:28]
    safe = title.replace("'", "").replace(":", "")
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,"
        f"drawtext=fontfile={fpath}:text=\"{safe}\":fontcolor=white:fontsize=48:"
        "box=1:boxcolor=black@0.65:boxborderw=14:x=(w-text_w)/2:y=28"
    )
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(wide),
           "-vf", vf, "-map", "0:v", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", str(out)]
    run(cmd)
    vcheck = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)], check=False)
    if "video" not in (vcheck.stdout or ""):
        raise RuntimeError("make_shorts produced no video stream")


def layout(segs: list[Seg], binfo: dict, song_start: float) -> float:
    grid = [b for b in binfo["beats"] if b >= song_start - 1e-3]
    if not grid:
        grid = [song_start]
    bi = 0
    for s in segs:
        s.t0 = grid[min(bi, len(grid) - 1)] - song_start
        s.t1 = grid[min(bi + s.beats, len(grid) - 1)] - song_start
        if s.t1 <= s.t0:
            s.t1 = s.t0 + s.beats * binfo["period"]
        bi += s.beats
    for s in segs:
        s.f0, s.f1 = int(round(s.t0 * FPS)), int(round(s.t1 * FPS))
        s.t0, s.t1 = s.f0 / FPS, s.f1 / FPS
    return segs[-1].t1 if segs else 0.0


def render(segs: list[Seg], song: Path, song_start: float | None, out: Path, mode: str,
           res: str, hook: str | None, font: str | None, black_tail: float = 0.6,
           workers: int = 2, crf: int = 16, pattern: str | None = None,
           slowed_reverb: bool = False, whisper_words: list[dict] | None = None) -> dict:
    W, H = map(int, res.lower().split("x"))
    fpath = CP.font_path(font)
    binfo = detect_beats(song)
    if song_start is None:
        song_start = pick_song_start(binfo, sum(s.beats for s in segs))
    total_cut = layout(segs, binfo, song_start)
    tmp = cache_dir() / f"tmp_{out.stem}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(lambda s: cut_segment(s, W, H, tmp), segs))
    tail_fr = int(round(black_tail * FPS))
    if tail_fr:
        blk = tmp / "black.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"color=black:s={W}x{H}:r={FPS}", "-frames:v", str(tail_fr),
             "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(blk)])
        parts.append(blk)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    base = tmp / "base.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(base)])
    nframes = (segs[-1].f1 if segs else 0) + tail_fr
    total = nframes / FPS
    wav = tmp / "mix.wav"
    mix_audio(song, song_start, total_cut, segs, wav, slowed_reverb=slowed_reverb)
    pat = CP.get(pattern) if pattern else CP.pick_pattern()
    # Load real Whisper words if the runner wrote them
    ww = whisper_words
    if ww is None:
        ww = load_whisper_map() or None
    if ww is None:
        wj = Path("whisper_words.json")
        if wj.exists():
            try:
                ww = json.loads(wj.read_text())
            except Exception:
                ww = None
    events = build_captions(segs, W, H, pat, base, whisper_words=ww)
    wide_out = out.with_suffix(".wide.mp4") if mode == "dual" else (out if mode == "wide" else tmp / "wide.mp4")
    composite(base, events, W, H, wav, wide_out, nframes, crf, fpath)
    shorts_out = None
    if mode in ("shorts", "dual"):
        shorts_out = out.with_suffix(".shorts.mp4") if mode == "dual" else out
        make_shorts(wide_out, shorts_out, hook or "", fpath)
    meta = {
        "duration": total, "shots": len(segs), "tempo": binfo["tempo"],
        "wide": str(wide_out), "shorts": str(shorts_out) if shorts_out else None,
        "pattern": pat["id"], "mode": mode, "hook": hook,
        "captions": len(events), "caption_text": [e["text"] for e in events],
        "dialogue_s": round(sum(s.t1 - s.t0 for s in segs if s.kind == "dialogue"), 2),
        "segments": [{"kind": s.kind, "src": Path(s.src).name, "start": round(s.start, 2),
                      "len": round(s.t1 - s.t0, 2)} for s in segs],
    }
    Path(str(out) + ".json").write_text(json.dumps(meta, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)
    return meta


# ---------- planning ----------
MIN_SRC_S = 20.0


def load_whisper_map() -> dict:
    wj = Path("whisper_words.json")
    if not wj.exists():
        return {}
    try:
        data = json.loads(wj.read_text())
    except Exception:
        return {}
    return data if isinstance(data, (dict, list)) else {}


def dialogue_windows(path: Path, words: list[dict] | None = None) -> list[dict]:
    """Real speech windows (2.5s-8.5s) built from Whisper word timings."""
    words = words or []
    wins = []
    cur = []
    for w in words:
        if cur and (w["s"] - cur[-1]["e"] > 0.7 or w["e"] - cur[0]["s"] > 8.5
                    or cur[-1]["word"].rstrip().endswith((".", "!", "?"))):
            wins.append(cur)
            cur = []
        cur.append(w)
    if cur:
        wins.append(cur)
    out = []
    for ws in wins:
        s, e = ws[0]["s"], ws[-1]["e"]
        if e - s < 1.2 or len(ws) < 3:
            continue
        if e - s < 2.5:
            e = s + 2.5
        text = " ".join(w["word"] for w in ws)
        out.append({"src": str(path), "s": s, "e": min(e, s + 8.5),
                    "score": len(ws) / max(1.0, e - s) + (1.0 if text.strip().endswith(("!", "?")) else 0),
                    "text": text})
    return out


def auto_plan(song: Path, clips: Path, target: float, binfo: dict,
              mode: str = "classic") -> list[Seg]:
    """Edit plan: real Whisper dialogue windows alternating with montage shots.

    Every shot uses a UNIQUE, non-overlapping range of source footage: no shot
    is ever repeated or looped. Sources shorter than 20s are refused.
    """
    period = binfo["period"]
    files = sorted(p for p in clips.iterdir() if p.suffix.lower() in VIDEO_EXT)
    durs = {str(f): probe_duration(f) for f in files}
    files = [f for f in files if durs[str(f)] >= MIN_SRC_S]
    if not files:
        raise RuntimeError(f"no source clip >= {MIN_SRC_S:.0f}s — refusing to loop short clips")
    wmap = load_whisper_map()
    used: dict[str, list[tuple[float, float]]] = {str(f): [] for f in files}

    def free(src, s, e):
        return s >= 0.3 and e <= durs[src] - 0.3 and all(e <= a or s >= b for a, b in used[src])

    def overlap(a, b):
        w1 = set(re.findall(r"[a-z]{3,}", a.lower()))
        w2 = set(re.findall(r"[a-z]{3,}", b.lower()))
        return len(w1 & w2) / max(1, min(len(w1), len(w2)))

    wins = []
    for f in files:
        wins += dialogue_windows(f, _words_for(str(f), wmap))
    total_beats = max(12, min(20, int(round(min(target, 24.0) / period))))
    dlg_budget = int(total_beats * 0.6)
    chosen = []
    for w in sorted(wins, key=lambda x: -x["score"]):
        if any(overlap(w["text"], c["text"]) >= 0.40 for c in chosen):
            continue
        db = int(math.ceil((w["e"] - w["s"] + 0.95) / period))
        if sum(c["beats"] for c in chosen) + db > dlg_budget:
            continue
        w["beats"] = db
        chosen.append(w)
        if len(chosen) >= 4:
            break
    chosen.sort(key=lambda c: (c["src"], c["s"]))
    for c in chosen:
        st = max(0.0, c["s"] - 0.25)
        used[c["src"]].append((st, st + c["beats"] * period + 0.3))

    rr = [0]

    def take(beats: int):
        need = beats * period + 0.4
        for k in range(len(files)):
            src = str(files[(rr[0] + k) % len(files)])
            t = 1.0
            while t + need <= durs[src] - 0.3:
                if free(src, t, t + need):
                    used[src].append((t, t + need))
                    rr[0] += 1
                    return src, t
                t += 0.5
        return None

    segs: list[Seg] = []
    beat_left = total_beats
    # 2s hook: open on the strongest montage shot
    first = take(2)
    if first:
        segs.append(Seg("montage", first[0], first[1], 2, zoom=1.06))
        beat_left -= 2
    for c in chosen:
        if beat_left <= 0:
            break
        segs.append(Seg("dialogue", c["src"], max(0.0, c["s"] - 0.25), c["beats"]))
        beat_left -= c["beats"]
        mb = min(4, beat_left)
        if mb > 0:
            t = take(mb)
            if t:
                segs.append(Seg("montage", t[0], t[1], mb, zoom=1.04))
                beat_left -= mb
    while beat_left > 0:
        b = min(3, beat_left)
        t = take(b)
        if not t:
            b = 1
            t = take(b)
            if not t:
                raise RuntimeError("not enough unique footage — refusing to repeat/loop shots")
        segs.append(Seg("montage", t[0], t[1], b, zoom=1.04))
        beat_left -= b
    print(f"PLAN: {len(segs)} shots, {len(chosen)} dialogue windows, "
          f"sources={[(Path(f).name, round(durs[str(f)], 1)) for f in files]}")
    return segs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("auto", "render"):
        p = sub.add_parser(name)
        p.add_argument("--song", required=True, type=Path)
        p.add_argument("--out", required=True, type=Path)
        p.add_argument("--mode", choices=["wide", "shorts", "dual"], default="dual")
        p.add_argument("--res", default="3840x2160")
        p.add_argument("--hook", default="")
        p.add_argument("--font", default=None)
        p.add_argument("--song-start", type=float, default=None)
        p.add_argument("--workers", type=int, default=2)
        p.add_argument("--crf", type=int, default=16)
        p.add_argument("--pattern", default=None)
        p.add_argument("--slowed-reverb", action="store_true")
        if name == "auto":
            p.add_argument("--clips", required=True, type=Path)
            p.add_argument("--duration", type=float, default=38.0)
            p.add_argument("--edit-mode", choices=["classic", "build_drop"], default="classic")
        else:
            p.add_argument("--plan", required=True, type=Path)
    a = ap.parse_args(argv)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.cmd == "auto":
        binfo = detect_beats(a.song)
        segs = auto_plan(a.song, a.clips, a.duration, binfo, a.edit_mode)
        render(segs, a.song, a.song_start, a.out, a.mode, a.res, a.hook, a.font,
               workers=a.workers, crf=a.crf, pattern=a.pattern,
               slowed_reverb=a.slowed_reverb)
    else:
        plan = json.loads(a.plan.read_text())
        segs = [Seg(**s) for s in plan.get("segments", [])]
        render(segs, a.song, a.song_start, a.out, a.mode, a.res, a.hook, a.font,
               workers=a.workers, crf=a.crf, pattern=a.pattern,
               slowed_reverb=a.slowed_reverb)


if __name__ == "__main__":
    main()
