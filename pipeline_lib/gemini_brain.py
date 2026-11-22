"""Gemini Vision brain (360p token saver). Pass 1 = director, Pass 2 = QC inspector. Zero Groq."""
from __future__ import annotations
import json, os, time
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

KEYS = [os.environ.get("GEMINI_API_KEY_1"), os.environ.get("GEMINI_API_KEY_2"), os.environ.get("GEMINI_API_KEY")]
KEYS = [k for k in KEYS if k]
# gemini-2.5-* now return 404 for these keys (Nov 2026); working 3.x models first, older fallbacks last.
MODELS = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]  # 3.8-flash-lite / 2.0-flash: 404 (Nov 2026)
QC_MODELS = MODELS

PROMPT = '''You are the director of a RIYIO cinematic short (vertical 4:5, 35-60s total). Genre: {genre}.
Watch this source clip (360p preview, timestamps in seconds) and return ONLY valid JSON with these keys:
{
  "reject": <bool>,
  "reject_reason": "<string>",
  "language": "<ISO code of the spoken dialogue, e.g. en>",
  "scene": "<show/movie, characters and the moment>",
  "dialogue_start": <seconds>,
  "dialogue_end": <seconds>,
  "punch_word": "<one word>",
  "punch_time": <seconds>,
  "action_cuts": [<12-20 timestamps in seconds>],
  "mood": "<dark_hype|epic_cinematic|emotional_romance|cold_sigma>",
  "hook_title": "<original 2-4 word title>",
  "hook_question": "<original 3-6 word question ending with ..?>",
  "post_caption": "<caption with credit: show name | channel | Edited under Fair Use>"
}
Rules:
- reject=true if the spoken dialogue is not English, if an OTT logo / channel watermark / burned-in subtitles
  are visible, or if the clip is a fan edit, compilation, reaction, review, movie trailer or music-only video.
  Genre notes: games = official game cinematics / cutscenes (allowed); sports = F1 team radio / onboard or
  football broadcast moments where English commentary or team radio counts as the dialogue (at least 5 words);
  anime = English dub only; cartoons = animated films / series in English.
- Pick the single most iconic, highest-tension CONTINUOUS English dialogue exchange. The dialogue window
  (dialogue_start..dialogue_end) must be 30-46 seconds long, start about 1 second before the first line,
  and end right after the punch word. Never choose dialogue_start < 15.0 if the clip is longer than 60s
  (skip YouTube intros / "Subscribe" / "Available in 4K" cards).
- punch_word = the last impactful word of the final line (a name, threat or reveal); punch_time = the exact
  second that word is spoken. The music drop will hit on it.
- action_cuts: 12-20 timestamps OUTSIDE the dialogue window showing the most intense visuals of the same
  show / characters (fights, reveals, close-ups); no logos, no text on screen.
- hook_title: an ORIGINAL 2-4 word title-style quote about THIS exact scene's theme. hook_question: an ORIGINAL
  question that makes people watch. Never reuse wording from these instructions; no cliches such as
  "Built different", "Full throttle", "She read him cold".
'''


def available() -> bool:
    return bool(KEYS) and genai is not None


def _parse_json(text: str):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    data = json.loads(text.strip())
    if isinstance(data, list):
        data = data[0] if data else {}
    return data


def _upload(client, path: Path):
    f = client.files.upload(file=str(path))
    for _ in range(60):
        state = getattr(getattr(f, "state", None), "name", "")
        if state == "ACTIVE":
            return f
        if state == "FAILED":
            raise RuntimeError("Gemini file processing failed")
        time.sleep(3)
        f = client.files.get(name=f.name)
    raise RuntimeError("Gemini file never became ACTIVE")


BUSY = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded", "high demand")


def _generate(make_contents, prompt: str, models: list[str], tag: str) -> tuple[dict, str]:
    """Try every key x model. Busy / quota errors (503 / 429) move to the next model at once;
    only after a whole round fails do we back off (10s, then 25s) and go round again."""
    last = None
    for rnd, wait in enumerate((0, 10, 25)):
        if wait:
            print(f"{tag}: all models busy, backing off {wait}s", flush=True)
            time.sleep(wait)
        for key in KEYS:
            client = genai.Client(api_key=key)
            try:
                contents, cleanup = make_contents(client)
            except Exception as e:
                last = e
                print(f"{tag} prepare error", repr(e)[:200], flush=True)
                continue
            try:
                for model in models:
                    try:
                        resp = client.models.generate_content(
                            model=model, contents=contents + [prompt],
                            config=types.GenerateContentConfig(temperature=0.3, response_mime_type="application/json"),
                        )
                        print(f"{tag} RAW ({model}):", (resp.text or "")[:700], flush=True)
                        return _parse_json(resp.text), model
                    except Exception as e:
                        last = e
                        busy = any(b in str(e) for b in BUSY)
                        print(f"{tag} {model} {'busy' if busy else 'error'}:", repr(e)[:140], flush=True)
                        continue
            finally:
                cleanup()
    raise RuntimeError(f"{tag} failed: {str(last)[:300]}")


def _ask(video: Path, prompt: str, models: list[str], tag: str) -> tuple[dict, str]:
    def make(client):
        f = _upload(client, video)

        def cleanup():
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass
        return [f], cleanup
    return _generate(make, prompt, models, tag)


PRESCREEN_PROMPT = """These are {n} still frames sampled across one YouTube upload. Check ONLY for overlays.
Return ONLY JSON: {{"clean": true, "logo": false, "subtitles": false, "fan_edit": false, "reason": ""}}
- logo = ANY channel/network/studio logo, bug or watermark anywhere (even small, in a corner).
- subtitles = burned-in subtitle / caption text.
- fan_edit = split screens, side-by-side comparisons, multi-feed compilations, reaction cams, text overlays.
clean = true only if all three are false."""


def prescreen(frames: list[Path]) -> dict:
    """Cheap pre-check on a few JPEG frames (no video upload) before the full director pass."""
    if not available():
        return {"clean": True, "reason": "gemini unavailable"}

    def make(client):
        parts = [types.Part.from_bytes(data=Path(fp).read_bytes(), mime_type="image/jpeg") for fp in frames]
        return parts, (lambda: None)
    order = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
    data, model = _generate(make, PRESCREEN_PROMPT.format(n=len(frames)), order, "PRESCREEN")
    flags = [k for k in ("logo", "subtitles", "fan_edit") if data.get(k)]
    clean = bool(data.get("clean", not flags)) and not flags
    return {"clean": clean, "flags": flags, "reason": data.get("reason") or ", ".join(flags), "model": model}


def analyze(video_360p: Path, genre: str = "movies") -> dict:
    """Pass 1: director."""
    if not available():
        raise RuntimeError("Gemini keys or google-genai missing")
    data, model = _ask(video_360p, PROMPT.replace("{genre}", genre), MODELS, "GEMINI")
    data["director_model"] = model
    return data


QC_PROMPT = """You are a strict QC inspector for a RIYIO 4:5 cinematic short. Intended structure:
1) Dialogue part (75-90% of runtime): one English scene (movie/series/game cutscene/anime dub/cartoon, or sports
   commentary / team radio) with original dialogue, framed without crop (blurred darkened fill above/below),
   a white top banner with black title text, 1-4 word captions placed BESIDE the speaking character (not
   covering faces) and revealed word by word in sync with the speech (first caption is a hook question).
   A dark music bed is audible under the dialogue the whole time.
2) The music drop hits exactly on the last punch word (white flash), the dialogue stops and the video cuts
   straight into a rapid montage (0.3-0.8s cuts, 5+ cuts) of the same show, music at full level, no captions.
   There is NO end card. A small white "RIYIO" watermark sits inside the movie picture, bottom-center.
Measured facts from the pipeline: {facts}
Fail if ANY: YouTube intro / "Subscribe" / "Available in 4K" card; more than ~1s before the first spoken word;
spoken language not English; captions missing, covering a face, or clearly out of sync with the speech;
black frames; music not audible at some point; drop not on the punch word or dead air before the montage;
an end card; watermark missing or on the black/blurred bars; total length outside 35-60 seconds;
ANY channel outro / end screen / "like & subscribe" graphic or promo speech ANYWHERE in the video (also mid-video),
or captions showing words like SUBSCRIBE / CHANNEL / SUPPORT US.
Return ONLY JSON:
{{"pass": true, "issues": [], "trim_start": 0.0, "trim_end": 0.0, "retry_new_clip": false}}
trim_start / trim_end = seconds to cut from the start / end only if a problem sits at an edge.
retry_new_clip = true if the source clip itself is unusable."""


def qc_inspect(video_360p: Path, facts: dict | None = None) -> dict:
    """Pass 2: inspect rendered draft (360p). qc_error is set only if Gemini is unreachable."""
    if not available():
        return {"pass": False, "issues": ["gemini unavailable"], "qc_error": "Gemini keys or google-genai missing"}
    try:
        data, model = _ask(video_360p, QC_PROMPT.format(facts=json.dumps(facts or {})), QC_MODELS, "QC")
    except Exception as e:
        return {"pass": False, "issues": [str(e)[:300]], "qc_error": str(e)[:300]}
    p = data.get("pass")
    return {
        "pass": (p.lower() == "true") if isinstance(p, str) else bool(p),
        "issues": list(data.get("issues") or []),
        "trim_start": float(data.get("trim_start") or 0.0),
        "trim_end": float(data.get("trim_end") or 0.0),
        "retry_new_clip": bool(data.get("retry_new_clip")),
        "model": model,
    }
