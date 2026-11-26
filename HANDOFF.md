# RIYIO Edits: handoff

This repo makes beat-synced 4K fan edits with RIYIO branding: 16:9 for YouTube and X, 9:16 for Instagram Reels. Songs come from the `songs-bank` release.

Everything runs on **GitHub Actions**. There are **no box scripts and no cron lines** for this repo (see `box/README.md`).

**Auto-post is OFF**, since BiBi's request on 2026-11-23: the daily crons are commented out, and posting also needs a repo variable.

Written 2026-11-26 (IST). All times are IST.

---

## 1. Cron lines

None on any computer. The only schedules are inside `.github/workflows/riyio-v2.yml`, and they are commented out (7 slots: 08:30, 12:30, 16:00, 18:30, 20:30, 22:30, 01:00 IST).

To turn auto-post back on:
1. Uncomment the `schedule:` block in `riyio-v2.yml`.
2. Set repo variable **`RIYIO_AUTO_PUBLISH=1`** (Settings → Secrets and variables → Actions → Variables).

Without that variable, every run is demo-only and nothing is posted.

## 2. Workflows and scripts

| File | What it does |
|---|---|
| `.github/workflows/riyio-v2.yml` → `run_v2.py` | The main pipeline:<br>• picks a source (`links/queue.txt`, `inbox/links/queue.json`, the `source_url` input, or search);<br>• picks montage shots (`config/shot_library.json` reuses good shots per title; no repeats in one video);<br>• picks a song by mood and tempo from `songs-bank`, least recently used first (`config/used_songs.json`);<br>• renders 4K with captions (P01–P20);<br>• uploads to the `media-cache` release, and posts through Buffer and YouTube only when not demo.<br>Dispatch inputs: `demo_only` (default true), `source_url`, `genre`. |
| `.github/workflows/sync_songs.yml` → `scripts/sync_songs_bank.py` | Downloads songs from `config/songs_catalog.json` that are missing from `songs-bank` (RapidAPI with key rotation), uploads them to the release, and writes BPM and mood tags. Inputs: `limit`, `budget_min` (default 300 min). A re-run continues where the last one stopped. |
| `scripts/tag_songs.py` | Tags library songs (BPM and mood) into `config/song_tags.json`. |
| `.github/workflows/produce.yml` → `run_real.py` | Legacy, manual only. |
| `pipeline_lib/`, `pipeline.py`, `vicestyle.py`, `remotion/` | Render code (Python plus the Remotion caption layer). |

## 3. GitHub Secrets (names only)

| Purpose | Secret names |
|---|---|
| Posting | `BUFFER_ACCESS_TOKEN` |
| AI | `GEMINI_API_KEY`, `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, `GROQ_API_KEY`, `GROQ_API_KEY_1` … `_4`, `OPENROUTER_API_KEY` |
| Downloads / search | `RAPIDAPI_KEY_1` … `_4`, `YT_RAPIDAPI_KEY_1` … `_4`, `YT_COOKIES` |
| Built in | `GITHUB_TOKEN` (automatic) |

Repo variable: `RIYIO_AUTO_PUBLISH`.

## 4. Where things live

| What | Where |
|---|---|
| Song list (target) | `config/songs_catalog.json`: 360 songs, 60 per mood (romance, hype, aggressive, emotional, epic, dark) |
| Song audio | Release **`songs-bank`** (`<mood>_<n>.mp3`) |
| Song rotation / tags | `config/used_songs.json`, `config/song_tags.json` |
| Shot library | `config/shot_library.json` |
| Rejected channels | `config/rejected_channels.json` |
| Rendered videos | Release **`media-cache`** |
| Source links queue | `links/queue.txt`, `links/used.txt`, `inbox/links/queue.json` |
| Post history | `history.json` |
| Allowed channels | `channels/channels.txt` |

## 5. Setting up a new computer

Nothing has to run on a computer.
- **To trigger runs:** install `gh`, run `gh auth login`, then run `gh workflow run riyio-v2.yml -R Bhupi820970/riyio-edits -f demo_only=true`, or use the Actions tab.
- **To run tests locally:** `bash box/setup_local.sh`, then `.venv/bin/python -m pytest -q`.

## 6. Known issues (2026-11-26)

- **Songs-bank is incomplete: 260 of 360 at 21:10 IST.**
  - Complete: romance, hype, aggressive and emotional (60/60 each).
  - **Missing: dark 50 and epic 50** (10/60 each).
  - The sync run `45839233344` (started 19:57 IST, 300-min budget) was still running at 21:10. If it stops before finishing, dispatch **Sync songs-bank** again; it only fetches the songs that are still missing.
  - Until then, dark and epic scenes have only 10 songs each, so songs repeat sooner.
- **`romance_10.mp3`, "Danza Kuduro (Slowed)" by Don Omar, is a slowed fan edit, not the original.** Swap it for the original "Danza Kuduro" (or another original romance song) in `config/songs_catalog.json`, delete that one asset from `songs-bank`, and re-run the sync.
- **Auto-post off:** see section 1.
- **Reference videos:** `ref1.mp4` and `ref2.mp4`, used for the look in `docs/REFERENCE_STYLE.md`, are not in git.
- **Quotas:** RapidAPI and Gemini are free tiers. When all keys hit their limit, the song sync and searches slow down. The keys rotate automatically.
