"""Gemini Vision brain. Token-saver 360p upload."""
from __future__ import annotations
import json, os, time
from pathlib import Path

try:
    from google import genai
except ImportError:
    genai = None

KEYS = [os.environ.get("GEMINI_API_KEY_1"), os.environ.get("GEMINI_API_KEY_2"), os.environ.get("GEMINI_API_KEY")]
KEYS = [k for k in KEYS if k]
MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

PROMPT = """Analyze this clip. Return ONLY JSON:
{"reject": false, "reject_reason": "", "dialogue_start": 10.0, "dialogue_end": 25.0, "action_cuts": [30.0, 35.0, 40.0, 45.0, 50.0], "hook": "She read him cold", "caption": "Instant read", "hashtags": ["#Edit"], "caption_y": "lower-center"}
reject=true if any logo/watermark/hardcoded subtitle. dialogue 15-22s high emotion. action_cuts 5-6 high-action timestamps. hook 3-5 words no cliches."""

def available():
    return bool(KEYS) and genai is not None

def analyze(video_360p: Path) -> dict:
    if not available():
        raise RuntimeError("Gemini not available")
    last = None
    for key in KEYS:
        for model in MODELS:
            try:
                client = genai.Client(api_key=key)
                f = client.files.upload(file=str(video_360p))
                while getattr(f.state, "name", "") == "PROCESSING":
                    time.sleep(2)
                    f = client.files.get(name=f.name)
                resp = client.models.generate_content(model=model, contents=[PROMPT, f])
                text = resp.text.strip()
                if text.startswith("```"):
                    text = text.split("```")[1].strip("json")
                data = json.loads(text)
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass
                return data
            except Exception as e:
                last = e
                if "429" in str(e):
                    continue
    raise RuntimeError(str(last))
