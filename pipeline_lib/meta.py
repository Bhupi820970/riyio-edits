"""Metadata generation via Groq (PRIMARY).

Uses llama-3.3-70b-versatile with the actual Whisper dialogue transcript to
write a short, savage, cold, high-curiosity 1-line hook (max 8-10 words) that is SPECIFIC to this exact scene and dialogue. NEVER use generic clichés like "Full throttle. Zero fear.", "Built different.", "Wrong man. Wrong night." or anything that could apply to any video., plus platform
titles/captions/hashtags.

The hook bar must NEVER show queue IDs / topic seeds / numbers. If Groq fails
twice, a clean fallback is built from the real Whisper dialogue, else from a
curated genre line list — never from the queue item.
"""
from __future__ import annotations

import json
import random
import re

from .groq_client import chat as groq_chat, available as groq_available, TEXT_MODEL

GENRE_LINES = {
    "movies": ["He walked in calm. Nobody walked out.", "Wrong man. Wrong night.",
               "They underestimated him once.", "Silence before the storm."],
    "series": ["Every empire falls from inside.", "Trust was the first casualty.",
               "One sentence changed everything."],
    "romance": ["She stayed when everyone left.", "Some goodbyes never end.",
                "Love made him dangerous."],
    "gaming": ["Los Santos never sleeps.", "No rules. No mercy.", "The city belongs to him now."],
    "sports": ["Pressure makes legends.", "They doubted. He delivered.", "Built different."],
    "racing": ["Second place is the first loser.", "Full throttle. Zero fear."],
    "anime": ["He stopped holding back.", "Power has a price.", "This is his final form."],
    "motivation": ["Nobody is coming to save you.", "Pain is the entry fee.",
                   "Discipline over everything."],
}

_ID_RE = re.compile(r"(\b[a-z]+_\d+(_\d+)?\b|\b\d{3,}\b|\b(queue|topic|demo)\b)", re.I)


def _strip_topic(topic: str) -> str:
    t = re.sub(r"\b[a-z]+_\d+_\d+\b", " ", topic or "", flags=re.I)
    t = re.sub(r"\b\d+\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def is_clean_hook(hook: str, topic: str = "", item_id: str = "") -> bool:
    h = (hook or "").strip().strip('"').strip()
    if len(h) < 6 or len(h.split()) < 2 or len(h.split()) > 12:
        return False
    if _ID_RE.search(h):
        return False
    low = h.lower()
    for bad in (item_id.lower(), topic.lower(), _strip_topic(topic).lower()):
        if bad and len(bad) > 4 and bad in low:
            return False
    if "_" in h or "#" in h:
        return False
    return True


def fallback_hook(genre: str, transcript: str = "") -> str:
    """Never returns IDs: best short Whisper line, else curated genre line."""
    sents = re.split(r"(?<=[.!?])\s+", transcript or "")
    cands = []
    for s in sents:
        s = re.sub(r"\s+", " ", s).strip(" -\"'")
        n = len(s.split())
        if 3 <= n <= 9 and not _ID_RE.search(s):
            score = (2 if s.endswith(("!", "?")) else 0) + (1 if n <= 7 else 0)
            cands.append((score, s))
    if cands:
        cands.sort(key=lambda x: -x[0])
        return cands[0][1].upper() if len(cands[0][1]) < 40 else cands[0][1]
    return random.choice(GENRE_LINES.get(genre) or GENRE_LINES["movies"])


def _ask_groq(genre: str, topic: str, transcript: str) -> dict | None:
    scene = _strip_topic(topic) or genre
    prompt = f"""You write metadata for a cold, high-retention cinematic {genre} fan-edit.

Scene type: {scene}
Exact dialogue from the clip (Whisper):
\"\"\"{transcript[:900]}\"\"\"

Rules:
- "hook": ONE savage, cold line (4-9 words) that fits THIS dialogue/scene.
  No numbers, no IDs, no hashtags, no emojis, no quotes, never generic filler.
- title_youtube: under 70 chars. caption_x: under 240 chars. caption_instagram: under 150 chars.
- hashtags: 5-7 relevant tags.
- description: one short line.

Reply JSON only:
{{"hook": "...", "title_youtube": "...", "caption_x": "...", "caption_instagram": "...",
"hashtags": ["#a", "#b", "#c", "#d", "#e"], "description": "..."}}"""
    raw = groq_chat([{"role": "user", "content": prompt}], model=TEXT_MODEL,
                    max_tokens=500, temperature=0.6)
    if not raw:
        return None
    try:
        s, e = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s:e])
    except Exception:
        return None


def generate_metadata(topic: str, genre: str, transcript: str = "", song_credit: str = "",
                      item_id: str = "") -> dict:
    data = None
    hook = ""
    source = "fallback"
    if groq_available():
        for _ in range(2):
            d = _ask_groq(genre, topic, transcript)
            if d:
                h = str(d.get("hook") or "").strip().strip('"').strip()
                if is_clean_hook(h, topic, item_id):
                    data, hook, source = d, h, "groq"
                    break
                print("META: rejected Groq hook:", h[:80])
                data = data or d
    else:
        print("META: Groq unavailable — using clean fallback hook")
    if not hook:
        hook = fallback_hook(genre, transcript)
    print(f"META: hook source = {source}")
    data = data or {}
    scene = _strip_topic(topic) or genre
    tags = data.get("hashtags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [t if str(t).startswith("#") else f"#{t}" for t in tags if not _ID_RE.search(str(t))][:7]
    for t in ("#RIYIO", f"#{genre}", "#edit", "#cinematic", "#fyp"):
        if len(tags) >= 5:
            break
        if t not in tags:
            tags.append(t)
    credit = song_credit or "Original Mix"
    desc = str(data.get("description") or f"{genre} edit").strip()
    if _ID_RE.search(desc):
        desc = f"{genre} edit"
    desc = desc + f"\n\nAudio: {credit}"

    def _clean(v, n):
        v = str(v or "").strip()
        return v[:n] if v and not _ID_RE.search(v) else hook[:n]

    return {
        "hook": hook[:80],
        "hook_source": source,
        "title_youtube": _clean(data.get("title_youtube"), 70),
        "caption_x": _clean(data.get("caption_x"), 240),
        "caption_instagram": _clean(data.get("caption_instagram"), 150),
        "hashtags": tags[:7],
        "description": desc,
        "song_name": credit,
        "scene": scene,
    }
