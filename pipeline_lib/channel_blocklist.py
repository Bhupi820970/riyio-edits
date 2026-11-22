"""Persistent learned blocklist of YouTube channels whose uploads were rejected for logos / watermarks /
burned-in subtitles / fan edits (config/rejected_channels.json). The workflow commits it back after each run."""
from __future__ import annotations
import json, re, time
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "config" / "rejected_channels.json"
LEARN = re.compile(r"logo|watermark|subtitle|caption text|burned|burnt|overlay|fan edit|fan-edit|compilation|"
                   r"splic|mashup|reaction|multiple languages|multi-language", re.I)


def _norm(ch: str) -> str:
    return re.sub(r"\s+", " ", (ch or "").strip().lower())


def load() -> dict:
    try:
        return json.loads(PATH.read_text()).get("channels", {})
    except Exception:
        return {}


def is_blocked(channel: str) -> bool:
    c = _norm(channel)
    return bool(c) and c in load()


def learn(channel: str, reason: str, title: str = "") -> bool:
    """Remember the channel if the reject reason is about overlays / fan edits. Returns True if stored."""
    c = _norm(channel)
    if not c or not LEARN.search(reason or ""):
        return False
    data = load()
    ent = data.get(c, {"count": 0})
    ent.update({"channel": channel, "reason": (reason or "")[:200], "example": (title or "")[:120],
                "last": time.strftime("%Y-%m-%d"), "count": int(ent.get("count", 0)) + 1})
    data[c] = ent
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps({"channels": dict(sorted(data.items()))}, indent=2, ensure_ascii=False) + "\n")
    print("BLOCKLIST + channel:", channel, "|", (reason or "")[:100], flush=True)
    return True
