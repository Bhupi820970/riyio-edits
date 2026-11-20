"""Helpers for reading clip links and local songs."""
from __future__ import annotations

from pathlib import Path


def load_clip_links(links_dir: Path | None = None) -> list[str]:
    """Read all non-comment lines from inbox/links/*.txt."""
    d = links_dir or Path("inbox/links")
    links = []
    if not d.exists():
        return links
    for f in d.glob("*.txt"):
        for line in f.read_text(errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("http"):
                links.append(line)
    return links


def mood_for_genre(genre: str) -> str:
    from .sourcing import GENRE_MOOD
    return GENRE_MOOD.get(genre, "epic")
