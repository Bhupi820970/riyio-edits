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
- First caption is a hook question at 0s (e.g. "WHAT MOTIVATES YOU..?").

## Look
- Grade: contrast ~1.25, saturation ~0.6, brightness ~0.9, teal/blue shadows (ref2 cold winter look), crushed blacks; film grain in darks.
- Sharpen: unsharp=5:5:1.0:5:5:0.0. ref1 is 60fps with optical-flow smoothness.
- Small creator watermark fades in and out (cursive), plus glowing brand at the end.

## BiBi's extra rules (Nov 22 2026)
- Total length 35-60s (target 40-55s). Phase 1 dialogue = ~75-90% of runtime.
- English-only scenes (whisper language='en'; non-English is rejected).
- Best quality: 1080p+ sources preferred, CRF ~16-18, sharpen + grade, final 4:5 upscale to 2160x2700.
- Gemini director picks the scene, exact timestamps, punch word, hook title and hook question (original per scene, never copied from prompt examples).
- No crop of the 16:9 source: blurred darkened fill top/bottom; white top hook banner with black bold title for the whole video.
- Montage: same show/character, 0.3-0.8s cuts on kicks, flash + zoom punch + slight RGB split + whoosh/hit SFX (self-generated only), no captions; end card glow "MADE BY RIYIO" + small RIYIO watermark.
- Reference videos are not committed (kept on the box at /workspace/riyio-ref/).
