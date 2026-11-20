# RIYIO Edits — v2 Automated 4K Fan-Edit Pipeline

Beat-synced cinematic fan-edit generator with RIYIO branding.

## Features
- 20 sleek compact beside-speaker caption patterns (P01–P20)
- 4K dual render: 16:9 YouTube/X + 9:16 Instagram Reels
- Uniform 21:9 letterbox bars
- YT_COOKIES bot-check bypass
- Strict 4-corner watermark rejection
- 30-video auto-refill queue
- Pre-upload QC gate
- Graceful multi-platform upload
- 7x daily GitHub Actions autopilot

## Quick start
```bash
pip install -r requirements.txt
# Download fonts into fonts/ (see produce.yml for the exact URLs)
python vicestyle.py auto --song song.mp3 --clips clips/ --out out.mp4 --mode dual
```

## Secrets (GitHub Actions)
Set these as repository secrets for full autopilot:
- YT_COOKIES, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
- X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
- IG_USER_ID, IG_ACCESS_TOKEN
- GEMINI_API_KEY_1..20 / GROQ_API_KEY / OPENROUTER_API_KEY
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

## Structure
- `vicestyle.py` — core 4K dual-render engine
- `caption_patterns.py` — 20 patterns + history tracking
- `pipeline_lib/` — sourcing, queue, QC, uploader
- `.github/workflows/produce.yml` — 7x daily IST schedule
