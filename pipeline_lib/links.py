"""Helpers for reading clip links and local songs."""
from __future__ import annotations

from pathlib import Path


def load_clip_links(links_dir: Path | None = None, genre: str | None = None) -> list[str]:
    """Read non-comment links from inbox/links/*.txt.

    Sections like '# === MOVIES ===' tag the following links with a genre;
    when `genre` is given only matching links are returned (max 3).
    """
    import re
    d = links_dir or Path("inbox/links")
    links = []
    if not d.exists():
        return links
    for f in sorted(d.glob("*.txt")):
        cur = None
        for line in f.read_text(errors="ignore").splitlines():
            line = line.strip()
            m = re.match(r"#\s*=+\s*([A-Za-z ]+?)\s*=+", line)
            if m:
                cur = m.group(1).strip().lower()
                continue
            if line and not line.startswith("#") and line.startswith("http"):
                if genre is None or (cur and cur.rstrip("s") == genre.lower().rstrip("s")):
                    links.append(line)
    return links[:3] if genre else links


def mood_for_genre(genre: str) -> str:
    from .sourcing import GENRE_MOOD
    return GENRE_MOOD.get(genre, "epic")
