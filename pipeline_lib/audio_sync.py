"""Beat detection + whisper words."""
from __future__ import annotations
from pathlib import Path

def detect_beats(song: Path) -> dict:
    try:
        import librosa
        y, sr = librosa.load(str(song), sr=22050, mono=True)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        beats = [float(b) for b in beats]
        drop = beats[len(beats)//3] if len(beats) > 3 else 8.0
        return {"tempo": float(tempo[0] if hasattr(tempo, "__len__") else tempo), "beats": beats, "drop": drop}
    except Exception:
        return {"tempo": 120.0, "beats": [i*0.5 for i in range(60)], "drop": 10.0}

def whisper_words(clip: Path) -> list:
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel("base.en", device="cpu", compute_type="int8")
        segs, _ = m.transcribe(str(clip), word_timestamps=True)
        out = []
        for s in segs:
            for w in (s.words or []):
                out.append({"word": w.word.strip(), "s": float(w.start), "e": float(w.end)})
        return out
    except Exception:
        return []
