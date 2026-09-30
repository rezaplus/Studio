---
name: reel-video-finishing
description: "Finish an existing vertical Reel locally with conservative 720p upscaling, adaptive sharpening, natural color grading, or controlled speed changes. Use after the visual story is approved; do not use it to generate new video."
---

# Reel Video Finishing

Create a new, reviewable local export from an approved Reel. Preserve the source file and its audio. This skill is for subtle finishing, not a substitute for native high-resolution generation.

## Choose the right operation

- Use the approved `natural-720p` preset for a 480x854 source that benefits from a cleaner 720x1280 delivery: Lanczos scaling, restrained adaptive sharpening, and a natural modern grade.
- Use a plain 720p upscale when resolution compatibility is the only goal. State that it does not add true source detail.
- Use a subtle grade only when the image needs less window highlight, slightly more depth, and a touch of warmth. Do not apply strong teal/orange looks, crush black clothing, or oversaturate plants and monitor blues.
- For captioning, word-timing, a fast-forward segment, or a countdown overlay, first read and use the sibling [reel-subtitles skill](../reel-subtitles/SKILL.md).

## Approved natural-720p recipe

Run the bundled script. It writes a new H.264/AAC-compatible MP4, preserves source audio, and refuses to overwrite an existing export:

```bash
python3 skills/reel-video-finishing/scripts/finish_reel.py \
  --video /absolute/path/input.mp4 \
  --output /absolute/path/output-720p.mp4 \
  --preset natural-720p
```

The preset is intentionally conservative: `720x1280` Lanczos scaling, `cas=0.20`, a gentle highlight roll-off, `contrast=1.04`, `saturation=1.025`, and a minimal warm color balance. Review both a face frame and a bright-window frame before treating it as final.

## Verify

1. Confirm 720x1280 video and an audio stream with `ffprobe`.
2. Inspect a face, a bright-window shot, the black outfit, text overlays, and fast movement for halos, clipped highlights, artificial skin, or flicker.
3. Report that it is a local upscale/grade, not native 720p generation.
