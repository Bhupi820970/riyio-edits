GENRE_MOOD = {
    "movies": "epic",
    "series": "emotional",
    "romance": "romance",
    "gaming": "aggressive",
    "sports": "aggressive",
    "racing": "aggressive",
    "anime": "epic",
    "motivation": "dark",
}


def pick_song_from_bank(genre: str, songs_dir: Path) -> Path | None:
    """Look for a matching mood .mp3 in songs/ or songs-bank release cache."""
    mood = GENRE_MOOD.get(genre, "epic")
    candidates = list(songs_dir.glob(f"*{mood}*.mp3")) + list(songs_dir.glob("*.mp3"))
    if candidates:
        return candidates[0]
    return None


def yt_song_cmd(query: str, out: Path) -> list[str]:
    """YouTube song download with PO Token provider + cookies + tv/mweb clients."""
    cmd = [
        "yt-dlp", "--no-playlist",
        "--js-runtimes", "deno",
        "--extractor-args", "youtube:player_client=tv,mweb",
        "-f", "ba/b",
        "-x", "--audio-format", "mp3",
        "-o", str(out),
        f"ytsearch1:{query}",
    ]
    # bgutil-ytdlp-pot-provider is used if installed
    cmd += ytdlp_cookie_args()
    return cmd