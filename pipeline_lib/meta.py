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


def generate_metadata(topic: str, genre: str, transcript: str = "", song_credit: str = "") -> dict:
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
        "description": f"{genre} edit — {topic}\n\nClip: {topic} | Audio: Original Mix",
        "song_name": "Original Mix",
    }
    if not groq_available():
        raise RuntimeError("Groq unavailable — refusing to fall back to queue ID for hook")

    prompt = f"""You are writing metadata for a cold, high-retention cinematic fan-edit.

Genre: {genre}
Topic: {topic}
Exact dialogue transcript from the scene (Whisper):
\"\"\"{transcript[:800]}\"\"\"

Rules:
- The hook MUST be short, savage, cold, and strictly based on THIS exact dialogue/scene.
- Never generic. Never use the topic string or any ID as the hook.
- Hook length: 1 line, max 8-10 words, punchy.
- Then write platform-optimized versions:
  - title_youtube: SEO-friendly, under 70 chars
  - caption_x: short, cold, under 240 chars
  - caption_instagram: short, cold, under 150 chars
- hashtags: exactly 5–7 relevant tags

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
        raise RuntimeError("Groq returned empty — refusing queue-ID hook fallback")
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            raise ValueError("no json")
        data = json.loads(raw[start:end])
        hook = (data.get("hook") or "").strip()
        # Reject hooks that look like queue IDs or the raw topic
        if not hook or any(x in hook.lower() for x in (topic.lower()[:20], "highlight", "9107", "race highlight")):
            raise ValueError(f"bad hook: {hook}")
        if len(hook.split()) > 12:
            hook = " ".join(hook.split()[:10])
        tags = data.get("hashtags") or []
        if not isinstance(tags, list):
            tags = []
        tags = [t if str(t).startswith("#") else f"#{t}" for t in tags][:7]
        while len(tags) < 5:
            tags.append("#RIYIO")
        desc = data.get("description") or f"{genre} edit"
        credit = song_credit or "Original Mix"
        if "Clip:" not in desc:
            desc = desc.rstrip() + f"\n\nClip: {topic} | Audio: {credit}"
        return {
            "hook": hook[:80],
            "title_youtube": (data.get("title_youtube") or hook)[:70],
            "caption_x": (data.get("caption_x") or hook)[:240],
            "caption_instagram": (data.get("caption_instagram") or hook)[:150],
            "hashtags": tags[:7],
            "description": desc,
            "song_name": credit,
        }
    except Exception as e:
        raise RuntimeError(f"Hook generation failed — no queue-ID fallback: {e}") from e
