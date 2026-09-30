#!/usr/bin/env python3
"""Render approved HeyGen Proofreads and assemble a localized Reel.

The source of subtitle text is always the reviewed provider SRT files. This
script deliberately contains no target-language speech-to-text step.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("heygen")
import workspace  # noqa: E402


def env() -> dict[str, str]:
    result = dict(os.environ)
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return result


def heygen(args: list[str], environment: dict[str, str]) -> dict:
    command = ["heygen", *args]
    completed = subprocess.run(command, cwd=ROOT, env=environment, check=True, text=True, capture_output=True)
    return json.loads(completed.stdout)


def nested(value: object, key: str) -> str | None:
    if isinstance(value, dict):
        if isinstance(value.get(key), str):
            return value[key]
        for item in value.values():
            found = nested(item, key)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = nested(item, key)
            if found:
                return found
    return None


def run(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def duration(file: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nokey=1:noprint_wrappers=1", str(file)], text=True).strip())


def clip(source: Path, start: float, end: float, target: Path) -> None:
    run(["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)])


def milliseconds(value: str) -> int:
    hours, minutes, tail = value.split(":")
    seconds, ms = tail.split(",")
    return int(hours) * 3_600_000 + int(minutes) * 60_000 + int(seconds) * 1000 + int(ms)


def stamp(value: int) -> str:
    value = max(0, round(value))
    hours, value = divmod(value, 3_600_000)
    minutes, value = divmod(value, 60_000)
    seconds, ms = divmod(value, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def shift_srt(content: str, offset: float, index: int) -> tuple[str, int]:
    blocks = re.split(r"\r?\n\s*\r?\n", content.strip())
    shifted: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        left, right = re.split(r"\s+-->\s+", lines[timing_index])
        lines[0] = str(index + 1)
        lines[timing_index] = f"{stamp(milliseconds(left) + int(offset * 1000))} --> {stamp(milliseconds(right) + int(offset * 1000))}"
        shifted.append("\n".join(lines))
        index += 1
    return "\n\n".join(shifted), index


def caption_from_srt(content: str) -> str:
    return " ".join(
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().isdigit() and "-->" not in line
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    review = json.loads(args.manifest.read_text(encoding="utf-8"))
    project = args.project.resolve()
    source = (ROOT / review["sourceVideo"]).resolve()
    work = project / "dubbing" / "fa-proofread-v1" / "render"
    work.mkdir(parents=True, exist_ok=True)
    environment = env()
    timeline: list[Path] = []
    cursor = 0.0
    subtitle_offset = 0.0
    subtitle_index = 0
    merged: list[str] = []

    for segment in review["segments"]:
        if segment["start"] > cursor + 0.01:
            gap = work / f"gap-{len(timeline):02}.mp4"
            clip(source, cursor, segment["start"], gap)
            timeline.append(gap)
            subtitle_offset += duration(gap)
        created = heygen(["video-translate", "proofreads", "generate", segment["proofreadId"], "--data", "{}"], environment)
        translation_id = nested(created, "video_translation_id") or nested(created, "id")
        if not translation_id:
            raise RuntimeError(f"No final translation ID for {segment['id']}")
        for attempt in range(120):
            status = heygen(["video-translate", "get", translation_id], environment)
            data = status.get("data", status)
            if data.get("status") == "completed":
                break
            if data.get("status") == "failed":
                raise RuntimeError(data.get("failure_message") or f"HeyGen failed {segment['id']}")
            time.sleep(10 if attempt < 12 else 30)
        else:
            raise TimeoutError(f"HeyGen timed out rendering {segment['id']}")
        video_url = nested(data, "video_url")
        if not video_url:
            raise RuntimeError(f"No final video URL for {segment['id']}")
        localized = work / f"{segment['id']}.fa.mp4"
        with urllib.request.urlopen(video_url) as response:
            localized.write_bytes(response.read())
        timeline.append(localized)
        shifted, subtitle_index = shift_srt(Path(segment["srt"]).read_text(encoding="utf-8"), subtitle_offset, subtitle_index)
        merged.append(shifted)
        subtitle_offset += duration(localized)
        cursor = segment["end"]
        print(f"Rendered {segment['id']}", flush=True)

    source_duration = duration(source)
    if cursor < source_duration - 0.01:
        tail = work / "tail.mp4"
        clip(source, cursor, source_duration, tail)
        timeline.append(tail)
    concat = work / "timeline.txt"
    concat.write_text("".join(f"file '{item.as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for item in timeline), encoding="utf-8")
    assembled = work / "reel-fa.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(assembled)])
    subtitles = work / "subtitles.fa.srt"
    subtitle_text = "\n\n".join(merged) + "\n"
    subtitles.write_text(subtitle_text, encoding="utf-8")
    captioned = work / "reel-fa-subtitles.mp4"
    run(["python3", "skills/reel-subtitles/scripts/burn_subtitles.py", "--video", str(assembled), "--subtitles", str(subtitles), "--output", str(captioned), "--preset", workspace.subtitle_preset()])
    run(["python3", "scripts/publish_to_studio.py", str(project), str(captioned), "--language", "fa", "--caption", caption_from_srt(subtitle_text), "--subtitles", str(subtitles), "--label", "HeyGen Precision Proofread dub — review", "--notes", "Per-spoken-beat HeyGen Precision lip-sync. Subtitle text comes from reviewed HeyGen target SRTs; no local Persian STT was used."])


if __name__ == "__main__":
    main()
