"""30-video pending backup queue + auto-refill.

Maintains inbox/queue.json. Tracks history for zero repeats.
When pending <= 6, notifies via Telegram (if configured) and refills to 30.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "inbox"
QUEUE_PATH = INBOX / "queue.json"
HISTORY_PATH = REPO / "history.json"

GENRES = ["movies", "series", "romance", "gaming", "sports", "racing", "anime", "motivation"]

GENRE_SEEDS = {
    "movies": ["epic movie scene", "cinematic dialogue", "blockbuster fight"],
    "series": ["tv series emotional scene", "series finale moment", "tv show best dialogue"],
    "romance": ["romantic movie scene", "love confession scene", "heartfelt couple moment"],
    "gaming": ["gta cinematic", "epic gaming moment", "open world scene"],
    "sports": ["sports highlight interview", "athlete press conference", "championship moment"],
    "racing": ["f1 race highlight", "car chase scene", "racing cinematic"],
    "anime": ["anime emotional scene", "anime fight scene", "anime best moment"],
    "motivation": ["motivational speech scene", "inspirational movie quote", "underdog story scene"],
}

SONG_MOODS = {
    "movies": "epic orchestral",
    "series": "dramatic score",
    "romance": "soft piano",
    "gaming": "trap beat",
    "sports": "hype anthem",
    "racing": "high energy electronic",
    "anime": "j-pop instrumental",
    "motivation": "uplifting cinematic",
}


def load_queue() -> list[dict]:
    if QUEUE_PATH.exists():
        try:
            return json.loads(QUEUE_PATH.read_text())
        except Exception:
            pass
    return []


def save_queue(q: list[dict]) -> None:
    INBOX.mkdir(exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(q, indent=2))


def load_history() -> dict:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except Exception:
            pass
    return {"uploaded": [], "source_ids": [], "used_patterns": [], "songs": []}


def save_history(h: dict) -> None:
    HISTORY_PATH.write_text(json.dumps(h, indent=2))


def pending_count(q: list[dict] | None = None) -> int:
    q = q if q is not None else load_queue()
    return sum(1 for item in q if item.get("status") == "pending")


def next_ready() -> dict | None:
    q = load_queue()
    for item in q:
        if item.get("status") == "pending":
            item["status"] = "processing"
            save_queue(q)
            return item
    return None


def mark_done(item_id: str, source_ids: list[str] | None = None, song: str | None = None) -> None:
    q = load_queue()
    h = load_history()
    for item in q:
        if item.get("id") == item_id:
            item["status"] = "done"
            break
    save_queue(q)
    h.setdefault("uploaded", []).append(item_id)
    if source_ids:
        h.setdefault("source_ids", []).extend(source_ids)
    if song:
        h.setdefault("songs", []).append(song)
    save_history(h)


def _notify_telegram(msg: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat, "text": msg}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def refill_queue(target: int = 30) -> int:
    q = load_queue()
    h = load_history()
    used = {item.get("topic", "").lower() for item in q}
    used.update(t.lower() for t in h.get("uploaded", []))
    added = 0
    attempts = 0
    while pending_count(q) < target and attempts < 200:
        attempts += 1
        genre = random.choice(GENRES)
        seeds = GENRE_SEEDS.get(genre, ["cinematic scene"])
        topic = f"{random.choice(seeds)} {random.randint(1, 9999)}"
        if topic.lower() in used:
            continue
        item = {
            "id": f"{genre}_{len(q) + 1}_{random.randint(1000, 9999)}",
            "genre": genre,
            "topic": topic,
            "search_queries": [topic, f"{topic} official", f"{topic} full scene"],
            "song_query": SONG_MOODS.get(genre, "cinematic"),
            "style_mode": "dual",
            "status": "pending",
        }
        q.append(item)
        used.add(topic.lower())
        added += 1
    save_queue(q)
    if added:
        _notify_telegram(f"RIYIO queue refilled: +{added} (now {pending_count(q)} pending)")
    return added


def ensure_queue(min_pending: int = 6, target: int = 30) -> None:
    if pending_count() <= min_pending:
        _notify_telegram(f"RIYIO queue low ({pending_count()} pending) — refilling to {target}")
        refill_queue(target)
