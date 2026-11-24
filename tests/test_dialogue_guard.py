"""Captions = the character's spoken line, never song lyrics (BiBi Nov 24 demo showed Mockingjay
'Hanging Tree' lyrics as captions)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline_lib import dialogue_guard as DG  # noqa: E402
from pipeline_lib import captions as C  # noqa: E402
from pipeline_lib import gemini_brain as GB  # noqa: E402


def W(text, t0=0.5, step=0.45):
    return [{"word": w, "s": t0 + i * step, "e": t0 + i * step + 0.35} for i, w in enumerate(text.split())]


HANGING = W("And if I ain't not hanging tree. Are you, are you coming", step=0.55)   # the failed demo's words
SPOKEN = W("Nice to meet you Mike. So you get real good at reading people, huh? No, no, no, no. "
           "What if you read about me first?")


def test_failed_demo_words_are_flagged_as_lyrics():
    why = DG.lyric_reasons(HANGING, 14.58, quote="", song_spans=None)
    assert any("repeated" in w for w in why), why
    quote = "They're going to bomb District 13. Destruction is coming, you won't survive the destruction"
    why = DG.lyric_reasons(HANGING, 14.58, quote=quote)
    assert any("do not match" in w for w in why)


def test_real_dialogue_passes():
    assert DG.lyric_reasons(SPOKEN, 30.0, quote="Nice to meet you Mike. You get real good at reading people") == []
    assert DG.repetition_score(SPOKEN) == 0.0          # "no, no, no, no" is talk, not a lyric hook


def test_music_marks_and_sung_spans():
    assert DG.lyric_reasons(W("\u266a are you coming to the tree \u266a now"), 0.0)
    why = DG.lyric_reasons(HANGING, 20.0, song_spans=[[19.0, 30.0]], check_quote=False)
    assert any("sung-song" in w for w in why)
    assert not any("sung-song" in w for w in DG.lyric_reasons(SPOKEN, 50.0, song_spans=[[0, 20]]))
    assert DG.clean_spans([[1, 2], {"start": 3, "end": 4}, ["x"], [5, 4]]) == [(1.0, 2.0), (3.0, 4.0)]


def test_filter_words_drops_sung_outside_and_song_title():
    words = W("we strike at dawn after dark after dark tonight", t0=0.2, step=0.5)
    words.append({"word": "montage", "s": 9.5, "e": 9.8})                   # past the dialogue end
    kept, dropped = DG.filter_words(words, end_s=6.0, window_start=10.0, song_spans=[[10.0, 10.6]],
                                    song_meta={"title": "After Dark"})
    txt = DG.words_text(kept).lower()
    assert "after" not in txt and "dark" not in txt and "montage" not in txt and "we" not in txt
    assert "strike" in txt and "tonight" in txt
    assert any("outside dialogue" in d for d in dropped) and any("song title" in d for d in dropped)
    assert any("sung part" in d for d in dropped)


def test_captions_never_leave_dialogue_section():
    evs = [{"start": -0.4, "end": 0.8}, {"start": 3.0, "end": 9.0}, {"start": 7.5, "end": 8.0}]
    out = DG.captions_in_window(evs, 7.3)
    assert len(out) == 2 and out[0]["start"] == 0.0 and out[1]["end"] == 7.3


def test_quote_overlap():
    assert DG.quote_overlap(SPOKEN, "nice to meet you mike") is None or DG.quote_overlap(SPOKEN, "nice to meet you mike") > 0.9
    assert DG.quote_overlap(SPOKEN, "reading people real good Mike") == 1.0
    assert DG.quote_overlap(SPOKEN, "ok") is None


def test_speech_scan_skips_sung_parts(monkeypatch):
    import run_v2
    sung = W("are you are you coming to the tree where they strung up a man", t0=0.0, step=0.4)
    talk = W("Plutarch listen to me they are going to bomb the dam tonight and nobody survives it", t0=30.0, step=0.4)
    monkeypatch.setattr(run_v2, "extract_wav", lambda *a, **k: Path("x.wav"))
    monkeypatch.setattr(run_v2, "whisper_words", lambda *a, **k: sung + talk)
    win = run_v2.find_speech_window(Path("s.mp4"), 300.0, length=19.0, scan=200.0, min_words=6,
                                    avoid=[[15.0, 21.0]])
    assert win and win[0] >= 15.0 + 29.0          # lo=15 (intro skip) + the spoken part at +30s


def test_transcription_uses_source_audio_only():
    src = (ROOT / "run_v2.py").read_text()
    assert 'Path("clips/dialogue.wav")' in src and "VOICE_BAND" in src
    assert "DG.lyric_reasons(words, ds, quote, sung, check_quote=not bad_plan)" in src
    assert "DG.filter_words(words, dialogue_frames / FPS, ds, sung, song_meta)" in src
    assert "captions look like song lyrics" in src


def test_gemini_prompts_ask_for_spoken_lines():
    assert "song_vocal_spans" in GB.PROMPT and "dialogue_quote" in GB.PROMPT and "never singing" in GB.PROMPT
    assert "captions_are_lyrics" in GB.QC_PROMPT and "caption_text" in GB.QC_PROMPT
    GB.QC_PROMPT.format(facts="{}")                   # still a valid format string


def test_qc_fails_on_lyric_captions(monkeypatch):
    monkeypatch.setattr(GB, "available", lambda: True)
    monkeypatch.setattr(GB, "_ask", lambda *a, **k: ({"pass": True, "issues": [], "captions_are_lyrics": True}, "m"))
    v = GB.qc_inspect(Path("x.mp4"), {})
    assert v["pass"] is False and v["captions_lyrics"] and "lyrics" in v["issues"][-1]
    monkeypatch.setattr(GB, "_ask", lambda *a, **k: ({"pass": True, "issues": [], "captions_match_dialogue": "false"}, "m"))
    assert GB.qc_inspect(Path("x.mp4"), {})["pass"] is False
    monkeypatch.setattr(GB, "_ask", lambda *a, **k: ({"pass": True, "issues": []}, "m"))
    assert GB.qc_inspect(Path("x.mp4"), {})["pass"] is True


def test_reference_caption_look_and_placement(monkeypatch):
    monkeypatch.delenv("CAPTION_STYLE", raising=False)
    st = C.pick_style("dark_hype", "x")
    assert st["id"] == "R00" and st["font"] == "playfair" and st["look"] == "glow" and st["place"] == "center"
    face = (0.40, 0.30, 0.60, 0.45)                   # speaker centred, like ref1/ref2 close-ups
    band = (140, 1290)
    x, y, align, ov, zone = C.place_center(300, 120, st, [face], face, 1080, 1350, band)
    assert align == "center" and ov == 0 and zone == "center-chin"
    assert abs((x + 150) - 540) < 5 and y >= 0.45 * 1350      # centred, just under the chin
    x, y, align, ov, zone = C.place_center(300, 120, st, [], None, 1080, 1350, band)
    assert zone == "center-noface" and abs((x + 150) - 540) < 5
    monkeypatch.setenv("CAPTION_STYLE", "P10")
    assert C.pick_style("dark_hype")["id"] == "P10"   # old speaker-side patterns still selectable
