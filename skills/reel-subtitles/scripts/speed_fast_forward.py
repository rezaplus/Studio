#!/usr/bin/env python3
"""Speed up one visual/audio interval in a video while retaining the surrounding timeline."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start", required=True, type=float)
    parser.add_argument("--end", required=True, type=float)
    parser.add_argument("--speed", required=True, type=float)
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg must be available on PATH.")
    if not args.video.is_file():
        raise RuntimeError(f"Video not found: {args.video}")
    if args.output.exists():
        raise RuntimeError(f"Output already exists: {args.output}")
    if args.end <= args.start or not 0.5 <= args.speed <= 2.0:
        raise RuntimeError("Use --end greater than --start and a --speed from 0.5 to 2.0.")

    graph = (
        f"[0:v]trim=0:{args.start},setpts=PTS-STARTPTS[v0];"
        f"[0:v]trim={args.start}:{args.end},setpts=(PTS-STARTPTS)/{args.speed}[v1];"
        f"[0:v]trim=start={args.end},setpts=PTS-STARTPTS[v2];"
        "[v0][v1][v2]concat=n=3:v=1:a=0[v];"
        f"[0:a]atrim=0:{args.start},asetpts=PTS-STARTPTS[a0];"
        f"[0:a]atrim={args.start}:{args.end},asetpts=PTS-STARTPTS,atempo={args.speed}[a1];"
        f"[0:a]atrim=start={args.end},asetpts=PTS-STARTPTS[a2];"
        "[a0][a1][a2]concat=n=3:v=0:a=1[a]"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-n", "-i", str(args.video), "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
            "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(args.output),
        ],
        check=True,
    )
    print(f"Sped-up video: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
