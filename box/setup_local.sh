#!/usr/bin/env bash
# Optional: prepare a Linux/macOS computer to run riyio-edits tests or a manual script locally.
# Production runs only on GitHub Actions; this installs nothing system-wide and starts nothing.
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
for t in git python3 ffmpeg gh; do command -v "$t" >/dev/null 2>&1 || echo "missing (install it): $t"; done
[ -d "$DIR/.venv" ] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/python" -m pip install -q --upgrade pip
"$DIR/.venv/bin/python" -m pip install -q -r "$DIR/requirements.txt" pytest
gh auth status >/dev/null 2>&1 && echo "gh: logged in" || echo "gh: run 'gh auth login' to dispatch workflows"
echo "ok. tests: $DIR/.venv/bin/python -m pytest -q"
