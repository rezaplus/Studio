#!/usr/bin/env python3
"""Burn a timed SRT or VTT file into a social-video deliverable with FFmpeg."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PRESETS = {
    "batimo": {
        "fontname": "Geeza Pro",
        "fontsize_ratio": 0.05,
        "outline": 2,
        "shadow": 1,
        "margin_v_ratio": 0.22,
    },
    "creator": {
        "fontname": "Avenir Next",
        "fontsize_ratio": 0.05,
        "outline": 2,
        "shadow": 1,
        "margin_v_ratio": 0.22,
    },
    "minimal": {
        "fontname": "Arial",
        "fontsize_ratio": 0.055,
        "outline": 2,
        "shadow": 0,
        "margin_v_ratio": 0.17,
    },
    "clean": {
        "fontname": "Avenir Next",
        "fontsize_ratio": 0.045,
        "outline": 0,
        "shadow": 1,
        "margin_v_ratio": 0.22,
    },
}


def probe_height(video: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "json",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    if not streams or not streams[0].get("height"):
        raise RuntimeError("Could not determine the source video height.")
    return int(streams[0]["height"])


def escape_filter_path(path: Path) -> str:
    return (
        path.resolve().as_posix()
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--subtitles", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preset", choices=PRESETS, default="creator", help="Use the content brand's subtitlePreset.")
    parser.add_argument("--font", help="Override the preset font for language coverage.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed and available on PATH.")
    if not args.video.is_file():
        raise RuntimeError(f"Video not found: {args.video}")
    if args.subtitles.suffix.lower() not in {".srt", ".vtt"} or not args.subtitles.is_file():
        raise RuntimeError("--subtitles must be an existing .srt or .vtt file.")
    if args.output.exists() and not args.overwrite:
        raise RuntimeError(f"Output already exists: {args.output}. Use --overwrite to replace it.")

    height = probe_height(args.video)
    preset = PRESETS[args.preset]
    # FFmpeg renders SRT through libass's 384x288 default script canvas.
    # Convert the desired output-pixel values to that canvas before applying
    # force_style, otherwise text becomes about height / 288 times too large.
    ass_reference_height = 288
    font_size = max(12, round(height * preset["fontsize_ratio"] * ass_reference_height / height))
    margin_v = max(24, round(height * preset["margin_v_ratio"] * ass_reference_height / height))
    style = (
        f"FontName={args.font or preset['fontname']},FontSize={font_size},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00101010,BackColour=&H80000000,Bold=1,Alignment=2,"
        f"Outline={preset['outline']},Shadow={preset['shadow']},MarginV={margin_v}"
    )
    subtitle_filter = f"subtitles=filename='{escape_filter_path(args.subtitles)}':force_style='{style}'"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y" if args.overwrite else "-n",
        "-i",
        str(args.video),
        "-vf",
        subtitle_filter,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(args.output),
    ]
    subprocess.run(command, check=True)
    print(f"Captioned video: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
