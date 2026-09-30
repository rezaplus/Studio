# BaTimo subtitle style

This is the default visual system for burned-in BaTimo Reel subtitles.

- Reference delivery: `BaTimo — phone experiment`, Persian `fa-v5`.
- Reference frame: `content/batimo-phone-experiment/edit/subtitle-style-reference/phone-experiment-fa-v5-subtitle-reference-12.2s.jpg` at 00:12.200.
- Font family: **Geeza Pro** for English, Persian, Turkish, and Arabic.
- Weight and color: bold, white (`#FFFFFF`).
- Legibility: restrained near-black outline (2) plus shadow (1); no solid subtitle box.
- Placement: centered lower-middle safe area, with a 22% bottom margin on a 9:16 Reel.
- Copy layout: one or two lines only; group spoken words into natural short phrases and keep text clear of faces and important actions.

Use `python3 skills/reel-subtitles/scripts/burn_subtitles.py --preset batimo`.
Do not silently use `creator`, `minimal`, `clean`, or a language-specific font
fallback. An exception requires explicit editorial approval.
