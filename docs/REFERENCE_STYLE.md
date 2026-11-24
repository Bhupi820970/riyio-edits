# RIYIO reference style (BiBi's permanent ideal, Nov 22 2026)
Source files: /workspace/riyio-ref/ref1.mp4 (720x800, 60fps, 59.6s), ref2.mp4 (720x900, 30fps, 46.5s)
BiBi rules: length 35s-60s; English captions synced to lips; best quality; Gemini picks best scene; match refs in everything.

## Structure
- Phase 1, about 75-90% of runtime: one continuous iconic dialogue scene (ref1 "Mike/Sharon reading people" interrogation, ref2 GoT Arya/Walder Frey "Winter came for House Frey"). Original dialogue at 100% volume, straight cuts on speaker changes, 2-5s shots.
- Music under the dialogue: dark, brooding synth, or eerie orchestral/choral, ducked about 10-12dB, building tension.
- Beat drop lands exactly on the last line's punch word ("MIKE", "WINTER CAME... for House Frey").
- Phase 2, 5-15s: phonk/dark-trap or epic hybrid drop at 0dB, dialogue muted, rapid montage of the same character/show (0.2-0.8s shots), every cut on a kick, with white flash (opacity 0.6 to 0 over 3 frames), zoom punch (1.1 to 1.0 over about 10 frames), slight RGB split, whoosh/sword hit SFX.
- No captions during the montage. Ending: branding card ("MADE BY ..." glow), about 1-3s.

## Framing
- Vertical 4:5-ish. 16:9 source centered, with either a heavily blurred (~50px) darkened copy of the video filling top and bottom, or pure black bars. Never crop the main video.
- ref1: a white top banner (~10% height) with black bold text hook title ("Money Really Talks"), from 1s to the end.

## Captions (the most important part)
- Centered in the middle of the frame over the video, not at the bottom. 1-4 words at a time, synced to syllables and lips (faster-whisper word timestamps).
- Serif font (Playfair Display / Garamond / Times bold look), mostly UPPERCASE, some italic sentence-case lines ("Okay..", "A little too perfect..").
- Pop-in spring: scale 1.2 to 1.0 over about 6 frames.
- Base white. Each caption group gets one accent color with matching glow (text-shadow ~15px): red, orange, pink, green, blue, yellow; the color rotates per line. Impact words sometimes use a transparent fill with red stroke ("WHAT", "MONEY"). Name or punch words get bigger and shake.
- NO opening question / hook caption (removed Nov 24 2026): captions appear only during the dialogue.

## Look
- Grade (Nov 24 2026, BiBi "jyada hi dark"): bright and natural, exposure within ~5% of the source: slight saturation pop (1.1), gentle mid/highlight curve, NO eq contrast / negative brightness / gamma / vignette / crushed blacks, light teal-orange, light grain. QC fails if the picture is >8% darker than the source frames.
- Sharpen: unsharp=5:5:1.0:5:5:0.0. ref1 is 60fps with optical-flow smoothness.
- Small creator watermark fades in and out (cursive), plus glowing brand at the end.

## BiBi's extra rules (Nov 22 2026)
- Total length 35-60s (target 40-55s). Phase 1 dialogue = ~75-90% of runtime.
- English-only scenes (whisper language='en'; non-English is rejected).
- Best quality: 1080p+ sources preferred, CRF ~16-18, sharpen + grade, final 4:5 upscale to 2160x2700.
- Gemini director picks the scene, exact timestamps, punch word, hook title and scene_mood (original per scene, never copied from prompt examples).
- No crop of the 16:9 source: blurred darkened fill top/bottom; white top hook banner with black bold title for the whole video.
- Montage: same show/character, 0.3-0.8s cuts on kicks, flash + zoom punch + slight RGB split + whoosh/hit SFX (self-generated only), no captions; end card glow "MADE BY RIYIO" + small RIYIO watermark.
- Reference videos are not committed (kept on the box at /workspace/riyio-ref/).

## Updates (Nov 22 2026, BiBi after the Gladiator demo) — these override the lines above
- Music never stops: the dark bed plays under the whole dialogue at about -11 dB (loudness-normalised, silent intros skipped), then the drop plays at 0 dB to the end.
- The drop lands exactly on the punch word (whisper word timestamps). When the punch word ends the dialogue stops and the video cuts straight into the montage (5-6+ cuts, no dead air).
- At most ~1s before the first spoken word; silent lead-in is trimmed. Total still 35-60s.
- NO end card ("MADE BY RIYIO" removed) and no cursive corner watermark.
- Watermark: "RIYIO" inside the movie picture, bottom-center, about 5-6% above the picture's bottom edge; small bold condensed sans (Anton, the same font as pro-edit's VICE CARTEL mark), text width ~7% of the frame width, white ~65% opacity, no glow (very faint shadow). Shown the whole video.
- Captions: speaker-side styles from pro-edit (caption_patterns.py P01-P15: beside the speaker, away from the face, never covering faces, Anton, black outline + hard shadow, 80%->100% pop, small white fillers, coloured key words) plus R00 = the reference serif glow look. Placement from YuNet face detection per caption; word-by-word reveal for lip sync. Styles rotate across videos, picked per mood.
- Genres rotate: movies, web series, games (official cinematics/cutscenes), sports (F1 team radio/overtakes, football commentary), anime (English dub), cartoons/animated films. Sports/games may use English commentary/team radio as dialogue (>= 5 words).
- Fonts are bundled in remotion/public/fonts (Anton, Playfair Display; SIL OFL).

## Update (Nov 23 2026, BiBi): pro-edit / Vice Cartel timeline — overrides structure + dialogue length above
Reference: https://youtu.be/ieltf77ofiA (made by pro-edit vicestyle.py, song ~128 BPM, 53 s). Measured:
| part | time | what |
|---|---|---|
| intro montage | 0-12.0 s | ~13 hard cuts on the beat (1-2 beats = 0.47-0.97 s, one 1.9 s), song at 100% |
| dialogue 1 | 12.0-24.8 s | 4 shots, speaker-side captions, song ducked under the voices |
| mid montage | 24.8-30.5 s | 7 beat cuts (0.47-1.9 s) |
| dialogue 2 | 30.5-41.7 s | 1 long shot, ends on the punch name "Lucia Caminos" |
| drop + outro montage | 41.7-52.0 s | ~20 cuts of 0.47-0.97 s on every 1-2 beats, song 100% |
| end | 52.0-52.5 s | cut to black, music off |

riyio (one source clip) uses the same shape with ONE middle dialogue:
- intro montage ~6-12 s (pro-edit hook_pat 2-2-2-1-1-2 beats), song full level, no caption over it.
- dialogue 8-18 s in the middle, pro-edit speaker-side captions (P01-P15 + R00 glow), song ducked to ~-11 dB.
- the song's drop beat lands exactly on the punch word (white flash + hit), dialogue stops, then a fast montage
  (4-cut flurry, then pro-edit end_pat 1-1-2-1 beats) with the song at full level to the end. Total ~42 s (35-59).
- one song plays continuously; video 0, the punch word and every montage cut sit on its beat grid
  (`style.plan_timeline`, tested in tests/test_timeline.py).
- Unchanged: no logos (source_url -> links/queue.txt -> channels/channels.txt -> search), RIYIO watermark,
  English, 2-pass Gemini QC, outro cut, no end card.
- Auto-post is OFF: schedule commented out in riyio-v2.yml and publishing needs repo variable RIYIO_AUTO_PUBLISH=1.

## Update (Nov 23 2026, BiBi after demo 6): variety, no repeats, multi-source, caption size
- Demo 6 problems: the whole edit came from one dinner-table clip, Gemini returned lazy picks (0,1,2,...80 s) so
  the montage was the same talking heads again and again; captions were 150-170 px (too big).
- Montage like ref1/ref2 (ref2 montage = 14 cuts in 23 s of DIFFERENT characters, scenes, wide + close + action):
  `pipeline_lib/montage_select.py` builds an inventory of camera shots (4 fps grey pass, shot cuts, <=2.5 s chunks,
  dHash per chunk). Every chunk is used once, picks in one source never overlap and keep >= 1 s apart, near-identical
  looks (dHash <= 10) are never used twice, the dialogue window is blocked, no two cuts in a row from one camera shot.
  Order with intent: intro = calmer build-up in story order, post-drop = strongest shots with rising energy, best last.
- Gemini director returns `montage_shots` (t, energy, kind, reason) = varied best moments that match the dialogue's
  vibe, plus `montage_sufficient`, `title`, `characters`, `related_queries`. Evenly spaced (lazy) picks are ignored.
- Multi-source: only if the main clip lacks enough unique / strong shots (or the director says so), download 1-2
  more clips of the SAME title (same trusted channel first, then search: official trailer / best scenes). Each extra
  gets RapidAPI 1080 download, resolution check, logo pre-screen, letterbox detection, Gemini same-story + shot pass;
  all sources are cut through the same 4:5 filter (1080 wide, grade, FPS) so they match.
- QC fails a repetitive / single-clip / unrelated montage and captions that are too big or too small.
- Captions: sized to the frame width like the refs (keys 52-96 px, fillers 34-60, punch up to 112), bigger for 1-2
  words, shrunk to the free space beside the speaker.
- Slow songs (beats > 0.75 s apart, librosa half-time) are subdivided so cuts land on 0.4-1.0 s.


## Nov 24 2026 update (BiBi)
- RIYIO watermark: half the old size (3.5% of the frame width, ~19 px at 1080) and glass-like: white at ~30% opacity,
  thin bright edge and a soft glow, no hard shadow. Still the only mark in the video.
- No opening question caption, ever (stripped from the Gemini plan, Remotion has no slot for it).
- Energy by sound: montage shots are scored by Gemini energy + frame motion + the source's own audio RMS peaks;
  the strongest shot lands on the drop (punch word), the next strongest on the hero cuts (longer beat holds).
- Song by mood: Gemini scene_mood (comedy/dark/epic/emotional/hype) -> only allowed song moods (no emotional song on a
  comedy scene), tempo-ranked from cached BPM tags (config/song_tags.json, scripts/tag_songs.py).
- Reference look: light film grain, light RGB split + hit SFX only on the drop / hero cuts, whoosh into hero cuts,
  60 fps output (motion-interpolated with scene-cut detection, falls back to frame doubling).
- Shot library: config/shot_library.json keeps the good shots per title (source id, timestamps, energy, type, hash);
  later videos of that title download those known-good sources first (fewer RapidAPI calls). No repeats per video.
