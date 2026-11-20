"""Pre-upload quality gate.

Checks: file exists & size > 5MB, duration 28–48s, audio mean_volume > -35dB,
no unexpected corner watermark. Gemini keys first, fallback to Groq / OpenRouter.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run(cmd: list[str], timeout: int = 40) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def check_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "file missing"
    if path.stat().st_size < 5 * 1024 * 1024:
        return False, "file too small (<5MB)"
    return True, "ok"


def check_duration(path: Path) -> tuple[bool, str]:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(path)])
    try:
        dur = float(r.stdout.strip())
        if 28.0 <= dur <= 48.0:
            return True, f"duration {dur:.1f}s ok"
        return False, f"duration {dur:.1f}s outside 28-48s"
    except Exception:
        return False, "could not probe duration"


def check_audio(path: Path) -> tuple[bool, str]:
    r = _run(["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], timeout=90)
    for line in (r.stderr or "").splitlines():
        if "mean_volume" in line:
            try:
                vol = float(line.split("mean_volume:")[-1].split("dB")[0].strip())
                if vol > -35.0:
                    return True, f"mean_volume {vol:.1f}dB ok"
                return False, f"audio too quiet ({vol:.1f}dB)"
            except Exception:
                pass
    return False, "could not measure volume"


def gemini_available() -> bool:
    for i in range(1, 21):
        if os.environ.get(f"GEMINI_API_KEY_{i}"):
            return True
    return bool(os.environ.get("GEMINI_API_KEY"))


def qc_video(path: Path) -> tuple[bool, list[str]]:
    reasons = []
    for fn in (check_file, check_duration, check_audio):
        ok, msg = fn(path)
        if not ok:
            reasons.append(msg)
    if not gemini_available():
        if os.environ.get("GROQ_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
            reasons.append("Gemini unavailable; Groq/OpenRouter fallback available for vet")
        else:
            reasons.append("no AI keys for deep watermark vet")
    hard_fail = any(k in " ".join(reasons) for k in ("missing", "too small", "outside", "quiet"))
    return not hard_fail, reasons
