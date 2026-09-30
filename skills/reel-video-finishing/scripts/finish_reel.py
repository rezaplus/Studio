#!/usr/bin/env python3
"""Create a conservative local finishing export for an approved vertical Reel."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PRESETS = {
    "upscale-720p": ["scale=720:1280:flags=lanczos", "format=yuv420p"],
    "natural-720p": [
        "scale=720:1280:flags=lanczos",
        "cas=0.20",
        "curves=all='0/0 0.50/0.49 0.80/0.78 1/0.95'",
        "eq=contrast=1.04:brightness=0.003:saturation=1.025",
        "colorbalance=rs=0.010:gs=0.004:bs=-0.010",
        "format=yuv420p",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preset", required=True, choices=PRESETS)
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed and available on PATH.")
    if not args.video.is_file():
        raise RuntimeError(f"Video not found: {args.video}")
    if args.output.exists():
        raise RuntimeError(f"Output already exists: {args.output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-n", "-i", str(args.video), "-vf", ",".join(PRESETS[args.preset]),
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-crf", "17",
            "-preset", "medium", "-c:a", "copy", "-movflags", "+faststart", str(args.output),
        ],
        check=True,
    )
    print(f"Finished Reel: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
