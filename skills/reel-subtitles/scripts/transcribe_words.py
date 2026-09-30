#!/usr/bin/env python3
"""Transcribe local video audio into one-word, timestamped SRT captions."""

from __future__ import annotations

import argparse
from pathlib import Path

from faster_whisper import WhisperModel


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="base")
    parser.add_argument("--language", default="en", help="Language code, or auto to detect it.")
    args = parser.parse_args()

    if not args.video.is_file():
        raise RuntimeError(f"Video not found: {args.video}")

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(args.video), language=None if args.language == "auto" else args.language,
        word_timestamps=True, vad_filter=True,
    )
    print(f"Language: {info.language}")
    entries: list[tuple[float, float, str]] = []
    for segment in segments:
        for word in segment.words or []:
            text = word.word.strip()
            if text:
                entries.append((word.start, word.end, text))

    if not entries:
        raise RuntimeError("No words were detected in the source audio.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index, (start, end, text) in enumerate(entries, start=1):
            # Keep the word visible through brief pauses but never overrun the next word.
            next_start = entries[index][0] if index < len(entries) else end + 0.08
            display_end = max(end, min(next_start - 0.02, end + 0.22))
            handle.write(
                f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(display_end)}\n{text}\n\n"
            )
    print(f"Word-timed transcript: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
