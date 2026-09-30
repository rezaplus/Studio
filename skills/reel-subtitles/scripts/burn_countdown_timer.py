#!/usr/bin/env python3
"""Burn a fast countdown timer into a vertical video while preserving audio."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def ass_time(seconds: float) -> str:
    centiseconds = round(max(0, seconds) * 100)
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    whole_seconds, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02}:{whole_seconds:02}.{centiseconds:02}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ass-output", required=True, type=Path)
    parser.add_argument("--start", required=True, type=float)
    parser.add_argument("--end", required=True, type=float)
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg must be available on PATH.")
    if not args.video.is_file():
        raise RuntimeError(f"Video not found: {args.video}")
    if args.end <= args.start or args.minutes < 1:
        raise RuntimeError("--end must be after --start and --minutes must be positive.")
    if args.output.exists():
        raise RuntimeError(f"Output already exists: {args.output}")

    duration = args.end - args.start
    step = duration / args.minutes
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 480
PlayResY: 854
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Timer,Avenir Next,40,&H00FFFFFF,&H000000FF,&H00000000,&H50000000,1,0,0,0,100,100,0,0,1,0,1,8,0,0,64,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = []
    for elapsed_minute in range(args.minutes + 1):
        start = args.start + elapsed_minute * step
        end = args.end + 0.3 if elapsed_minute == args.minutes else args.start + (elapsed_minute + 1) * step
        remaining = args.minutes - elapsed_minute
        events.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Timer,,0,0,64,,{remaining:02}:00"
        )
    args.ass_output.parent.mkdir(parents=True, exist_ok=True)
    args.ass_output.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    escaped_ass = str(args.ass_output.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    subprocess.run(
        [
            "ffmpeg", "-n", "-i", str(args.video), "-vf", f"ass=filename='{escaped_ass}'",
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-c:a", "copy", "-movflags", "+faststart", str(args.output),
        ],
        check=True,
    )
    print(f"Countdown ASS: {args.ass_output.resolve()}")
    print(f"Countdown video: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
