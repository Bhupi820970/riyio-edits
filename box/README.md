# Box side for riyio-edits

Riyio needs **no box scripts and no cron**. Everything runs on GitHub Actions: `riyio-v2.yml`, `sync_songs.yml` and `produce.yml`.

Kept outside git on purpose:
- **The reference videos `ref1.mp4` and `ref2.mp4`** (see `docs/REFERENCE_STYLE.md`). Videos are never committed.
- **YouTube browser login.** It exists only as a GitHub Secret, never as a file in the repo.

The optional local tools below are for checking things by hand. They are not needed in production:

```
python3 -m pip install -r requirements.txt   # same packages the workflows use
python3 -m pytest -q                         # unit tests
```

See `box/setup_local.sh`.
