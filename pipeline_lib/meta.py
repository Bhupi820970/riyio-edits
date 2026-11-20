"""Metadata generation via Groq (PRIMARY).

Uses llama-3.3-70b-versatile with the actual Whisper dialogue transcript
+ topic/genre to write a short, savage, cold, high-retention hook that
strictly matches the exact scene (never generic / off-topic).

Also returns platform-optimized title / caption and 5–7 relevant hashtags
for YouTube, X, and Instagram (via Buffer).
"""
from __future__ import annotations

import json

from .groq_client import chat as groq_chat, available as groq_available, TEXT_MODEL


def generate_metadata(topic: str, genre: str, transcript: str = "") -> dict:
    """Return platform-optimized metadata.

    Keys:
      hook, title_youtube, caption_x, caption_instagram,
      hashtags (list of 5-7), description
    """
    fallback = {
        "hook": topic[:80],
        "title_youtube": f"RIYIO | {topic[:70]}",
        "caption_x": topic[:200],
        "caption_instagram": topic[:150],
        "hashtags": ["#RIYIO", f"#{genre}", "#edit", "#cinematic", "#viral"],
        "description": f"{genre} edit — {topic}",
    }
    if not groq_available():
        return fallback

    prompt = f"""You are writing metadata for a cold, high-retention cinematic fan-edit.

Genre: {genre}
Topic: {topic}
Exact dialogue transcript from the scene (Whisper):
\"\"\"{transcript[:800]}\"\"\"

Rules:
- The hook MUST be short, savage, cold, and strictly based on THIS exact dialogue/scene.
- Never generic. Never off-topic. Never invent lines that are not in the transcript.
- Hook length: 1 line, max ~12 words, punchy.
- Then write platform-optimized versions:
  - title_youtube: SEO-friendly, under 70 chars, includes the hook energy
  - caption_x: short, cold, under 240 chars
  - caption_instagram: short, cold, under 150 chars (no long paragraphs)
- hashtags: exactly 5–7 relevant tags (include genre + scene-specific, no spam)

Reply with JSON only, no markdown:
{{
  "hook": "...",
  "title_youtube": "...",
  "caption_x": "...",
  "caption_instagram": "...",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
  "description": "one short line"
}}
"""
    raw = groq_chat(
        [{"role": "user", "content": prompt}],
        model=TEXT_MODEL,
        vision=False,
        max_tokens=500,
        temperature=0.35,
    )
    if not raw:
        return fallback
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            tags = data.get("hashtags") or fallback["hashtags"]
            if not isinstance(tags, list):
                tags = fallback["hashtags"]
            tags = [t if t.startswith("#") else f"#{t}" for t in tags][:7]
            while len(tags) < 5:
                tags.append("#RIYIO")
            return {
                "hook": (data.get("hook") or fallback["hook"])[:120],
                "title_youtube": (data.get("title_youtube") or fallback["title_youtube"])[:70],
                "caption_x": (data.get("caption_x") or fallback["caption_x"])[:240],
                "caption_instagram": (data.get("caption_instagram") or fallback["caption_instagram"])[:150],
                "hashtags": tags[:7],
                "description": data.get("description") or fallback["description"],
            }
    except Exception:
        pass
    return fallback
