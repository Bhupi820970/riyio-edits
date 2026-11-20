import json
from pathlib import Path

CATALOG_PATH = Path("config/songs_catalog.json")


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text()).get("songs", [])


def pick_song_from_catalog(genre: str, used: set[str] | None = None) -> dict | None:
    """Pick a non-repeating mood-matched song from the catalog.
    Returns the catalog entry (file, mood, title, artist).
    """
    mood = GENRE_MOOD.get(genre, "epic")
    songs = [s for s in load_catalog() if s.get("mood") == mood]
    if not songs:
        songs = load_catalog()
    if not songs:
        return None
    used = used or set()
    fresh = [s for s in songs if s["file"] not in used]
    pool = fresh or songs
    return pool[0]


def songs_bank_url(filename: str) -> str:
    return f"https://github.com/Bhupi820970/riyio-edits/releases/download/songs-bank/{filename}"