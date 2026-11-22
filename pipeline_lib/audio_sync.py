"""Beat drop detection + word-level Whisper."""
from __future__ import annotations
from pathlib import Path

def detect_beats(song: Path) -> dict:
    try:
        import librosa
        import numpy as np
        y, sr = librosa.load(str(song), sr=22050, mono=True)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        beats = [float(b) for b in beats]
        # beat drop approx: max onset strength in second half
        onset = librosa.onset.onset_strength(y=y, sr=sr)
        drop_idx = int(np.argmax(onset[len(onset)//3:])) + len(onset)//3
        drop_t = float(librosa.frames_to_time(drop_idx, sr=sr))
        return {"tempo": float(np.atleast_1d(tempo)[0]), "beats": beats, "drop": drop_t}
    except Exception:
        return {"tempo": 120.0, "beats": [i * 0.5 for i in range(80)], "drop": 12.0}

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _MODEL


def whisper_words(clip: Path) -> list[dict]:
    """Word-level timestamps (seconds, relative to clip start)."""
    try:
        segments, _ = _model().transcribe(str(clip), word_timestamps=True)
        words = []
        for seg in segments:
            for w in (seg.words or []):
                txt = (w.word or "").strip()
                if txt:
                    words.append({"word": txt, "s": float(w.start), "e": float(w.end)})
        return words
    except Exception as e:
        print("WHISPER error:", repr(e)[:300], flush=True)
        return []
