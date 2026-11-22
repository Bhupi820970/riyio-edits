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

def whisper_words(clip: Path) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(clip), word_timestamps=True)
        words = []
        for seg in segments:
            for w in (seg.words or []):
                words.append({"word": w.word.strip(), "s": float(w.start), "e": float(w.end)})
        return words
    except Exception:
        return []
