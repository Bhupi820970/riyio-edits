"""links/queue.txt -> next unused YouTube link; results logged to links/used.txt (committed back by the workflow)."""
from __future__ import annotations
import re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "links" / "queue.txt"
USED = ROOT / "links" / "used.txt"
YT = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|live/)|youtu\.be/)[\w\-]{6,}[^\s#]*")


def _vid(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([\w\-]{6,})", url)
    return m.group(1) if m else url.strip()


def used_ids() -> set[str]:
    out = set()
    if USED.exists():
        for ln in USED.read_text().splitlines():
            parts = ln.split("\t")
            if len(parts) >= 3 and not ln.startswith("#"):
                out.add(_vid(parts[2]))
    return out


def pending() -> list[str]:
    if not QUEUE.exists():
        return []
    done, out = used_ids(), []
    for ln in QUEUE.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = YT.search(ln)
        if m and _vid(m.group(0)) not in done and m.group(0) not in out:
            out.append(m.group(0))
    return out


def mark(url: str, status: str, reason: str = "") -> None:
    USED.parent.mkdir(parents=True, exist_ok=True)
    with USED.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(time.time() + 19800))} IST\t{status}\t{url}\t{(reason or '').replace(chr(9), ' ')[:200]}\n")
    print("LINK", status, url, reason[:120], flush=True)
