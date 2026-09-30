---
name: reel-subtitles
description: "Create burned-in, creator-style subtitles for vertical social videos from an approved SRT or VTT transcript. Use when a Reel, TikTok, or short-form video needs readable timed captions; do not use for in-app caption publishing."
---

# Reel Subtitles

Create a local, reviewable captioned video. Preserve the source video; write a new output rather than overwriting it.

## Inputs and scope

- Require a timed `.srt` or `.vtt` transcript. Do not invent dialogue or timestamps.
- For a spoken-language change, get the intended caption language before creating the transcript.
- Default to burned-in subtitles for delivery. Keep a separate caption file alongside the output for accessibility and later edits.
- Do not upload, publish, or send the video anywhere unless the user explicitly asks.

## Reel styling

- Use the content brand's `subtitlePreset` (`config/brands/<brand>/brand.json`, resolved by `scripts/workspace.py`; default `creator`). Keep it consistent for every language of that brand and never switch presets without the user's approval. The bundled presets are `creator`, `minimal`, `clean` and `batimo` (Geeza Pro, bold white, dark outline/shadow, lower-middle 9:16 safe area; see `references/batimo-subtitle-style.md`).
- Use at most two lines. Split captions at natural phrase boundaries; do not place text over faces or product details.
- Keep on-screen wording faithful to the approved dialogue. Small punctuation cleanup is fine; do not alter claims or CTAs.
- Do not add a generated logo, watermarks, fake chat bubbles, or other UI merely because captions are being added.
- When the user asks for word-level timing, transcribe the local audio first and review its wording against the approved dialogue before rendering. Use the `clean` preset when they prefer no visible text border.

## Render

Use the bundled script with an explicit output path:

```bash
python3 skills/reel-subtitles/scripts/burn_subtitles.py \
  --video /absolute/path/input.mp4 \
  --subtitles /absolute/path/captions.srt \
  --output /absolute/path/output-captioned.mp4 \
  --preset creator   # or the brand's subtitlePreset
```

The script preserves the original audio, burns captions into a newly encoded H.264 video, and refuses to overwrite an existing file unless `--overwrite` is supplied.

For local word-timed captions, run the bundled transcriber through `uv` (it downloads the selected open Whisper model the first time):

```bash
uv run --with faster-whisper --with "av>=13,<16" python skills/reel-subtitles/scripts/transcribe_words.py \
  --video /absolute/path/input.mp4 \
  --output /absolute/path/word-timed.srt \
  --language en
```

For an approved fast-forward time-passage cue, use `burn_countdown_timer.py`. It places a clean timer in the upper safe area and preserves the existing audio and captions.

Use `speed_fast_forward.py` before the timer when the user wants the visual break itself to pass more quickly. Recalculate the countdown end time after changing speed.

## Verify

1. Inspect the finished file with `ffprobe`: it must retain a video stream and the original audio stream.
2. Extract and visually inspect frames during the opening, a dense two-line caption, and the final CTA. Check timing, line breaks, contrast, and lower safe-zone placement.
3. Report the output path and whether captions were burned in. State explicitly if the transcript was supplied rather than transcribed.
