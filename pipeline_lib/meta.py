"""Metadata generation via Groq (PRIMARY).

Uses llama-3.3-70b-versatile for titles, descriptions, hashtags.
Gemini / OpenRouter are optional fallbacks only.
"""
from __future__ import annotations

from .groq_client import chat as groq_chat, available as groq_available, TEXT_MODEL


def generate_metadata(topic: str, genre: str, transcript: str = "") -> dict:
    """Return {"title": str, "description": str, "hashtags": list[str]}."""
    if not groq_available():
        return {
            "title": f"RIYIO | {topic[:60]}",
            "description": f"{genre} edit — {topic}",
            "hashtags": ["#RIYIO", f"#{genre}"],
        }
    prompt = (
        f"Generate YouTube/X metadata for a cinematic {genre} fan-edit.\n"
        f"Topic: {topic}\n"
        f"Transcript snippet: {transcript[:400]}\n\n"
        "Reply with JSON only:\n"
        '{"title": "...", "description": "...", "hashtags": ["#tag1", "#tag2"]}'
    )
    raw = groq_chat(
        [{"role": "user", "content": prompt}],
        model=TEXT_MODEL,
        vision=False,
        max_tokens=400,
        temperature=0.4,
    )
    if not raw:
        return {
            "title": f"RIYIO | {topic[:60]}",
            "description": f"{genre} edit — {topic}",
            "hashtags": ["#RIYIO"],
        }
    try:
        import json
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            return {
                "title": data.get("title") or f"RIYIO | {topic[:60]}",
                "description": data.get("description") or topic,
                "hashtags": data.get("hashtags") or ["#RIYIO"],
            }
    except Exception:
        pass
    return {
        "title": f"RIYIO | {topic[:60]}",
        "description": raw[:300],
        "hashtags": ["#RIYIO", f"#{genre}"],
    }
