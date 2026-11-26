"""Tag every songs-bank track once (BPM + mood + loudness) into config/song_tags.json (cached, committed back).
Runs in GitHub Actions (riyio-v2.yml) only for songs that have no tag yet, so after the first run it is a no-op."""
from __future__ import annotations
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_lib import song_mood as SM  # noqa: E402
from pipeline_lib.sourcing import download_bank_song, bank_assets  # noqa: E402
from pipeline_lib.audio_sync import detect_beats  # noqa: E402


def song_rms(path: Path) -> float | None:
    try:
        import librosa
        import numpy as np
        y, _ = librosa.load(str(path), sr=22050, mono=True, duration=120)
        return float(np.sqrt(np.mean(y ** 2)))
    except Exception:
        return None


def main(budget_s: float = 900.0):
    tags = SM.load_tags()
    t0, done = time.time(), 0
    tmp = Path("clips/tag_song.mp3")
    for s in SM.only_available(SM.load_catalog(), bank_assets()):   # skip catalog songs not in the bank
        f = s.get("file")
        if not f or (tags.get(f) or {}).get("bpm"):
            continue
        if time.time() - t0 > budget_s:
            print("TAG budget reached, rest next run", flush=True)
            break
        got = download_bank_song(f, tmp)
        if not got:
            continue
        b = detect_beats(got)
        tags[f] = SM.tag_entry(s.get("mood") or "", b.get("tempo") or 0, song_rms(got), b.get("drop"))
        done += 1
        print("TAG", f, tags[f], flush=True)
        SM.save_tags(tags)
    tmp.unlink(missing_ok=True)
    print(f"TAGGED {done} new songs; {len(tags)} cached", flush=True)


if __name__ == "__main__":
    main()
