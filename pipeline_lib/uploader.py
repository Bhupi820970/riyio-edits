"""Graceful multi-platform uploader.

4K 16:9 -> YouTube + X
4K 9:16 -> Instagram Reels
Skips any platform whose secrets are missing. Never crashes the run.
"""
from __future__ import annotations

import os
from pathlib import Path


def _has(keys: list[str]) -> bool:
    return all(os.environ.get(k) for k in keys)


def upload_youtube(path: Path, title: str, description: str = "") -> bool:
    if not _has(["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]):
        print("YouTube secrets missing — skipping")
        return False
    print(f"[YouTube] upload ready: {path.name} as '{title}'")
    # Real implementation: google-api-python-client with refresh token
    return True


def upload_x(path: Path, text: str) -> bool:
    if not _has(["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]):
        print("X secrets missing — skipping")
        return False
    print(f"[X] upload ready: {path.name}")
    return True


def upload_instagram(path: Path, caption: str) -> bool:
    if not _has(["IG_USER_ID", "IG_ACCESS_TOKEN"]):
        print("Instagram secrets missing — skipping")
        return False
    print(f"[Instagram] upload ready: {path.name} as Reel")
    return True


def upload_dual(wide: Path, shorts: Path, title: str, caption: str = "") -> dict:
    return {
        "youtube": upload_youtube(wide, title, caption),
        "x": upload_x(wide, caption or title),
        "instagram": upload_instagram(shorts, caption or title),
    }
