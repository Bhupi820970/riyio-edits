"""Gemini Vision brain. Token-saver 360p. Zero Groq."""
from __future__ import annotations
import json, os, time
from pathlib import Path

try:
    from google import genai
except ImportError:
    genai = None

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
                for _ in range(30):
                    if getattr(getattr(f, "state", None), "name", "") != "PROCESSING":
                        break
                    time.sleep(2)
                    f = client.files.get(name=f.name)
                resp = client.models.generate_content(model=model, contents=[PROMPT, f])
                text = (resp.text or "").strip()
                if text.startswith("```"):
                    text = text.split("```")[1].lstrip("json").strip()
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
