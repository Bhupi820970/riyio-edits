"""Automatic Groq API key rotation (PRIMARY AI engine).

Keys: GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4,
then fallback GROQ_API_KEY if set.

On HTTP 429 / quota / auth error, the key is marked cooled-down and the next
available key is used immediately. Never fails the pipeline solely due to one key.
"""
from __future__ import annotations

import os
import time
from typing import Any

import urllib.request
import urllib.error
import json

GROQ_BASE = "https://api.groq.com/openai/v1"

# Vision models for 4-corner watermark vetting + scene selection
VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]
# Text model for metadata generation
TEXT_MODEL = "llama-3.3-70b-versatile"

_COOLDOWN: dict[str, float] = {}   # key -> unix time when it can be used again
_COOLDOWN_SEC = 60 * 15            # 15 min temporary cool-down


def _all_keys() -> list[str]:
    keys = []
    for i in range(1, 5):
        k = (os.environ.get(f"GROQ_API_KEY_{i}") or "").strip()
        if k:
            keys.append(k)
    fallback = (os.environ.get("GROQ_API_KEY") or "").strip()
    if fallback and fallback not in keys:
        keys.append(fallback)
    return keys


def _usable_keys() -> list[str]:
    now = time.time()
    return [k for k in _all_keys() if _COOLDOWN.get(k, 0) <= now]


def _mark_cooled(key: str) -> None:
    _COOLDOWN[key] = time.time() + _COOLDOWN_SEC


def _call(key: str, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{GROQ_BASE}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:500]
        if e.code in (429, 401, 403) or "quota" in body.lower() or "rate" in body.lower():
            _mark_cooled(key)
            raise RuntimeError(f"groq key cooled ({e.code}): {body}") from e
        raise RuntimeError(f"groq http {e.code}: {body}") from e


def chat(messages: list[dict], model: str | None = None, vision: bool = False,
         max_tokens: int = 1024, temperature: float = 0.2) -> str | None:
    """Rotate through available Groq keys. Returns assistant text or None if all keys fail."""
    model = model or (VISION_MODELS[0] if vision else TEXT_MODEL)
    keys = _usable_keys()
    if not keys:
        return None
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    last_err = None
    for key in keys:
        try:
            data = _call(key, payload)
            choices = data.get("choices") or []
            if choices:
                return (choices[0].get("message") or {}).get("content")
        except Exception as e:
            last_err = e
            continue
    # try alternate vision model once if vision and first failed
    if vision and model == VISION_MODELS[0] and len(VISION_MODELS) > 1:
        payload["model"] = VISION_MODELS[1]
        for key in _usable_keys():
            try:
                data = _call(key, payload)
                choices = data.get("choices") or []
                if choices:
                    return (choices[0].get("message") or {}).get("content")
            except Exception:
                continue
    return None


def available() -> bool:
    return bool(_usable_keys())
