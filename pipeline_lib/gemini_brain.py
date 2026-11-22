"""Gemini Vision brain. Token-saver 360p. Zero Groq."""
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
MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"]

PROMPT = '''Analyze this movie/series/sports clip. Return ONLY valid JSON:
{
  "reject": false,
  "reject_reason": "",
  "dialogue_start": 12.0,
  "dialogue_end": 28.0,
  "action_cuts": [40.0, 45.5, 51.0, 56.2, 62.0],
  "mood": "dark_hype",
  "hook": "She read him cold",
  "post_caption": "Clip: Movie Name | Credit: Channel | Edited under Fair Use.",
  "hashtags": ["#MovieEdit", "#Viral"],
  "caption_y": "lower-center"
}
Rules:
- reject=true if ANY OTT logo, watermark, or hardcoded subtitle is visible.
- dialogue_start must be >= 15.0 if the clip is longer than 60s (skip YouTube intros / "Subscribe" / "Available in 4K" cards).
- dialogue_start/end: 15-22 seconds of highest-emotion punchy dialogue.
- action_cuts: exactly 5-6 timestamps of high-action or close-up shots.
- mood: one of "dark_hype", "epic_cinematic", "emotional_romance", "cold_sigma".
- hook: raw specific 3-5 words. NO cliches like "Built different" or "Full throttle".
- caption_y: "lower-center" or "middle-lower".
- post_caption: include auto-credit for fair use.
'''

def available() -> bool:
    return bool(KEYS) and genai is not None

def analyze(video_360p: Path) -> dict:
    if not available():
        raise RuntimeError("Gemini keys or google-genai missing")
    last = None
    for key in KEYS:
        for model in MODELS:
            try:
                client = genai.Client(api_key=key)
                f = client.files.upload(file=str(video_360p))
                for _ in range(60):
                    state = getattr(getattr(f, "state", None), "name", "")
                    print("gemini file state:", state)
                    if state == "ACTIVE":
                        break
                    if state == "FAILED":
                        raise RuntimeError("Gemini file processing failed")
                    time.sleep(3)
                    f = client.files.get(name=f.name)
                else:
                    raise RuntimeError("Gemini file never became ACTIVE")
                resp = client.models.generate_content(model=model, contents=[PROMPT, f])
                text = (resp.text or "").strip()
                if text.startswith("```"):
                    text = text.split("```")[1].lstrip("json").strip()
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
                print("GEMINI RAW:", text[:500], flush=True)
                data = json.loads(text)
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass
                return data
            except Exception as e:
                last = e
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    continue
    raise RuntimeError(f"Gemini failed: {last}")


QC_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"] + [m for m in MODELS if not m.startswith("gemini-2.5")]

QC_PROMPT = """You are a strict QC inspector for a 4:5 short-form edit. Intended structure:
1) Dialogue part: a movie/series/anime/sports scene with its original dialogue, word-by-word captions
   in the lower-center, a white hook bar at the top during the first 6 seconds, RIYIO watermark at bottom.
2) At the end of the dialogue: a short white flash (beat drop), then 5-6 rapid action cuts (0.5-0.8s each)
   with music only and no captions.
Check strictly for: YouTube intros / "Subscribe" / "Available in 4K" cards, missing or out-of-sync captions
during the dialogue, black-screen frames (a single white flash frame is intended), broken or missing beat drop.
Return ONLY JSON:
{"pass": true, "issues": [], "trim_start": 0.0, "trim_end": 0.0, "retry_new_clip": false}
trim_start / trim_end = seconds to cut from the start / end if a problem sits only at an edge.
retry_new_clip = true if the source clip itself is unusable."""


def _parse_json(text: str):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    data = json.loads(text.strip())
    if isinstance(data, list):
        data = data[0] if data else {}
    return data


def qc_inspect(video_360p: Path) -> dict:
    """Pass 2: inspect rendered draft (360p). Returns normalized verdict; qc_error set if Gemini unreachable."""
    if not available():
        return {"pass": False, "issues": ["gemini unavailable"], "qc_error": "Gemini keys or google-genai missing"}
    last = None
    for key in KEYS:
        try:
            client = genai.Client(api_key=key)
            f = client.files.upload(file=str(video_360p))
            for _ in range(60):
                state = getattr(getattr(f, "state", None), "name", "")
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    raise RuntimeError("Gemini file processing failed")
                time.sleep(3)
                f = client.files.get(name=f.name)
        except Exception as e:
            last = e
            print("QC upload error", repr(e)[:200], flush=True)
            continue
        for model in QC_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[f, QC_PROMPT],
                    config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
                )
                data = _parse_json(resp.text)
                verdict = {
                    "pass": bool(data.get("pass")) if not isinstance(data.get("pass"), str) else data.get("pass").lower() == "true",
                    "issues": list(data.get("issues") or []),
                    "trim_start": float(data.get("trim_start") or 0.0),
                    "trim_end": float(data.get("trim_end") or 0.0),
                    "retry_new_clip": bool(data.get("retry_new_clip")),
                    "model": model,
                }
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass
                return verdict
            except Exception as e:
                last = e
                print(f"QC {model} error", repr(e)[:200], flush=True)
                continue
    return {"pass": False, "issues": [str(last)[:300]], "qc_error": str(last)[:300]}
