"""RapidAPI YouTube downloader with key rotation.
Uses YT_RAPIDAPI_KEY_1..4 and host youtube-info-download-api.p.rapidapi.com
"""
from __future__ import annotations
import os
import time
import requests
from typing import Optional

HOST = "youtube-info-download-api.p.rapidapi.com"

def get_keys() -> list[str]:
    keys = []
    for i in range(1, 5):
        k = os.environ.get(f"YT_RAPIDAPI_KEY_{i}", "").strip()
        if k:
            keys.append(k)
    return keys

class YTRapidClient:
    def __init__(self):
        self.keys = get_keys()
        self.idx = 0
        self.cooldown: dict[str, float] = {}

    def _next(self) -> Optional[str]:
        if not self.keys:
            return None
        now = time.time()
        for _ in range(len(self.keys)):
            k = self.keys[self.idx % len(self.keys)]
            self.idx += 1
            if self.cooldown.get(k, 0) < now:
                return k
        return None

    def download(self, url: str, fmt: str = "mp3") -> Optional[str]:
        """Return direct download URL or None."""
        for _ in range(max(1, len(self.keys) * 2)):
            key = self._next()
            if not key:
                time.sleep(1)
                continue
            headers = {"x-rapidapi-key": key, "x-rapidapi-host": HOST}
            try:
                r = requests.get(
                    f"https://{HOST}/ajax/download.php",
                    headers=headers,
                    params={"url": url, "format": fmt},
                    timeout=30,
                )
                if r.status_code in (429, 403, 401):
                    self.cooldown[key] = time.time() + 90
                    continue
                if r.status_code == 200:
                    data = r.json()
                    return data.get("download_url") or data.get("url") or data.get("link") or data.get("progress_url")
            except Exception:
                self.cooldown[key] = time.time() + 30
        return None

yt_client = YTRapidClient()
