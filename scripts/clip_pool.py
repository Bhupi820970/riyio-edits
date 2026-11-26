#!/usr/bin/env python3
"""Top up the riyio clip pool (release `clip-pool`), see pipeline_lib/clip_pool.py.

  python3 scripts/clip_pool.py refill [--max 20] [--budget-min 150]
  python3 scripts/clip_pool.py status

Sources: trusted official channels (channels/channels.txt) first, then the run_v2 genre searches.
Rules (same as riyio-v2): official / trusted uploads, no fan edits, learned channel blocklist, >=1080p,
30 s+, 5-frame Gemini pre-screen (no burned-in subtitles / logos / watermarks) when Gemini is available.
Errors are retried with backoff; whatever is still missing is fetched on the next scheduled run.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline_lib import clip_pool as P  # noqa: E402

WORK = Path("/tmp/riyio_pool")


def genres() -> dict[str, list[str]]:
    """GENRES literal from run_v2.py (parsed as data, not imported/executed)."""
    tree = ast.parse((ROOT / "run_v2.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "GENRES" for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def probe(p: Path) -> tuple[int, int, float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True, timeout=60)
    try:
        d = json.loads(r.stdout or "{}")
        s = (d.get("streams") or [{}])[0]
        return int(s.get("width") or 0), int(s.get("height") or 0), float((d.get("format") or {}).get("duration") or 0)
    except ValueError:
        return 0, 0, 0.0


def screen(p: Path, dur: float) -> str | None:
    try:
        from pipeline_lib.gemini_brain import prescreen, available
    except Exception:
        return None
    if not available():
        return None
    frames = []
    for k, frac in enumerate((0.12, 0.3, 0.5, 0.7, 0.88)):
        fp = WORK / f"screen_{k}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{dur * frac:.2f}", "-i", str(p),
                        "-frames:v", "1", "-vf", "scale=768:-2", "-q:v", "4", str(fp)], timeout=60)
        if fp.exists():
            frames.append(fp)
    if not frames:
        return None
    ps = prescreen(frames)
    return None if ps.get("clean") else f"pre-screen: {ps.get('reason') or ps.get('flags')}"


def candidates(doc: dict) -> list[dict]:
    from pipeline_lib import channel_source, channel_blocklist
    from pipeline_lib.sourcing import search_candidates
    skip = P.known_ids(doc)
    out = []
    try:
        for v in channel_source.candidates(skip):
            if not channel_blocklist.is_blocked(v.get("channel") or ""):
                out.append({**v, "genre": v.get("genre") or "trusted"})
    except Exception as e:
        print("channel candidates error:", repr(e)[:160])
    for g, qs in genres().items():
        for q in qs:
            try:
                for it in search_candidates(q + (" official" if g in ("sports", "games") else " scene official clip"),
                                            exclude=set())[:3]:
                    if P.vid_of(it.get("url") or "") not in skip:
                        out.append({**it, "genre": g})
            except Exception as e:
                print("search error:", q[:40], repr(e)[:120])
                time.sleep(5)
    seen, uniq = set(), []
    for c in out:
        v = P.vid_of(c.get("url") or "")
        if v and v not in seen:
            seen.add(v)
            uniq.append(c)
    return P.balanced_order(uniq, list(genres()) + ["trusted"])


def refill(max_new: int, budget_min: float) -> int:
    from pipeline_lib.sourcing import download_url, rapid_available, AllKeysExhausted
    if not rapid_available():
        print("no RapidAPI keys -> nothing to do")
        return 0
    doc = P.load(WORK)
    refilling, want = P.refill_plan(doc)
    doc["refilling"] = refilling
    print(f"pool: {len(P.usable(doc))} usable, refilling={refilling}, want +{want}")
    if not want:
        P.save(doc, WORK)
        return 0
    t0, added = time.time(), 0
    P.ensure_release()
    for c in candidates(doc):
        if added >= min(want, max_new) or time.time() - t0 > budget_min * 60:
            break
        vid = P.vid_of(c["url"])
        f = WORK / f"{vid}.mp4"
        info = None
        for attempt in range(3):            # retry with backoff on transient errors
            try:
                info = download_url(c["url"], f)
                break
            except AllKeysExhausted:
                print("RapidAPI quota out -> stop; next scheduled run continues")
                P.save(doc, WORK)
                return added
            except Exception as e:
                print(f"download error ({attempt + 1}/3):", repr(e)[:120])
                time.sleep(20 * (3 ** attempt))
        if not info or not f.exists():
            continue
        w, h, dur = probe(f)
        why = None
        if max(w, h) < P.MIN_LONG_SIDE:
            why = f"below 1080p ({w}x{h})"
        elif dur < 30:
            why = f"too short ({dur:.0f}s)"
        else:
            why = screen(f, dur)
        if why:
            print("reject", vid, why)
            doc["clips"].append({"id": vid, "url": c["url"], "title": (c.get("title") or "")[:160],
                                 "channel": c.get("channel") or "", "genre": c["genre"], "file": "",
                                 "state": "rejected", "note": why[:160]})
            f.unlink(missing_ok=True)
            continue
        up = None
        for attempt in range(3):
            up = P.gh("release", "upload", P.RELEASE, str(f), "--repo", P.repo(), "--clobber", timeout=900)
            if up.returncode == 0:
                break
            time.sleep(15 * (attempt + 1))
        f.unlink(missing_ok=True)
        if up.returncode != 0:
            continue
        doc["clips"].append({"id": vid, "url": c["url"], "title": (c.get("title") or info.get("title") or "")[:160],
                             "channel": c.get("channel") or info.get("channel") or "", "genre": c["genre"],
                             "file": f"{vid}.mp4", "w": w, "h": h, "dur": round(dur, 1),
                             "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "state": "ready"})
        added += 1
        print(f"added {vid} [{c['genre']}] {w}x{h} {dur:.0f}s {(c.get('title') or '')[:60]}")
        if added % 5 == 0:
            P.save(doc, WORK)
    doc["refilling"], _ = P.refill_plan(doc)
    P.save(doc, WORK)
    print(f"pool now {len(P.usable(doc))} usable (+{added})")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["refill", "status"])
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--budget-min", type=float, default=150)
    a = ap.parse_args()
    if a.cmd == "status":
        doc = P.load(WORK)
        print(json.dumps({"usable": len(P.usable(doc)), "refilling": doc.get("refilling"),
                          "total_entries": len(doc.get("clips") or [])}))
        return
    refill(a.max, a.budget_min)


if __name__ == "__main__":
    main()
