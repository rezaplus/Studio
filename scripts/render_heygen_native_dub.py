#!/usr/bin/env python3
"""Render approved per-beat proofreads and assemble a native-resolution Reel."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("heygen")


def env() -> dict[str, str]:
    result = dict(os.environ)
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return result


def heygen(args: list[str], environment: dict[str, str]) -> dict:
    run = subprocess.run(["heygen", *args], cwd=ROOT, env=environment, text=True, capture_output=True)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or run.stdout.strip())
    return json.loads(run.stdout)


def find(data: object, key: str) -> str | None:
    if isinstance(data, dict):
        own = data.get(key)
        if isinstance(own, str):
            return own
        for child in data.values():
            found = find(child, key)
            if found:
                return found
    if isinstance(data, list):
        for child in data:
            found = find(child, key)
            if found:
                return found
    return None


def duration(path: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nokey=1:noprint_wrappers=1", str(path)], text=True).strip())


def run(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def cut(source: Path, start: float, end: float, target: Path) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-to", str(end), "-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-crf", "16", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)])


def milliseconds(stamp: str) -> int:
    h, m, tail = stamp.split(":")
    s, ms = tail.split(",")
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def stamp(value: int) -> str:
    h, value = divmod(max(0, value), 3_600_000)
    m, value = divmod(value, 60_000)
    s, ms = divmod(value, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def shift_srt(text: str, offset: float, first_index: int) -> tuple[str, int]:
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    output: list[str] = []
    index = first_index
    for block in blocks:
        lines = block.splitlines()
        line_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if line_index is None:
            continue
        left, right = re.split(r"\s+-->\s+", lines[line_index])
        lines[0] = str(index)
        lines[line_index] = f"{stamp(milliseconds(left) + round(offset * 1000))} --> {stamp(milliseconds(right) + round(offset * 1000))}"
        output.append("\n".join(lines))
        index += 1
    return "\n\n".join(output), index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sessions_path = args.sessions.resolve()
    sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
    base = sessions_path.parent
    source = (ROOT / sessions["sourceVideo"]).resolve()
    output = args.output.resolve()
    work = base / "render"
    work.mkdir(parents=True, exist_ok=True)
    environment = env()

    for segment in sessions["segments"]:
        response = heygen(["video-translate", "proofreads", "generate", segment["proofreadId"], "--data", "{}"], environment)
        render_id = find(response, "video_translation_id") or find(response, "id")
        if not render_id:
            raise RuntimeError(f"No render ID returned for {segment['id']}")
        segment["renderId"] = render_id
    (work / "renders.json").write_text(json.dumps(sessions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("All Persian lip-sync renders started.", flush=True)

    pending = list(sessions["segments"])
    for attempt in range(120):
        remaining: list[dict] = []
        for segment in pending:
            status = heygen(["video-translate", "get", segment["renderId"]], environment)
            data = status.get("data", status)
            if data.get("status") == "completed":
                url = find(data, "video_url")
                if not url:
                    raise RuntimeError(f"No video URL for {segment['id']}")
                target = work / f"{segment['id']}.fa.mp4"
                with urllib.request.urlopen(url) as response:
                    target.write_bytes(response.read())
                segment["renderedVideo"] = str(target.relative_to(ROOT))
                print(f"Rendered {segment['id']}", flush=True)
            elif data.get("status") == "failed":
                raise RuntimeError(data.get("failure_message") or f"Render failed for {segment['id']}")
            else:
                remaining.append(segment)
        if not remaining:
            break
        pending = remaining
        time.sleep(10 if attempt < 12 else 30)
    else:
        raise TimeoutError("One or more HeyGen renders did not complete in time")

    clips: list[Path] = []
    captions: list[str] = []
    cursor = 0.0
    offset = 0.0
    caption_index = 1
    for segment in sessions["segments"]:
        if segment["start"] > cursor + 0.005:
            gap = work / f"gap-{len(clips):02}.mp4"
            cut(source, cursor, segment["start"], gap)
            clips.append(gap)
            offset += duration(gap)
        localized = ROOT / segment["renderedVideo"]
        clips.append(localized)
        shifted, caption_index = shift_srt((ROOT / segment["srt"]).read_text(encoding="utf-8"), offset, caption_index)
        captions.append(shifted)
        offset += duration(localized)
        cursor = segment["end"]
    source_duration = duration(source)
    if cursor < source_duration - 0.005:
        tail = work / "tail.mp4"
        cut(source, cursor, source_duration, tail)
        clips.append(tail)
    concat = work / "timeline.txt"
    concat.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)])
    subtitles = output.with_suffix(".srt")
    subtitles.write_text("\n\n".join(captions) + "\n", encoding="utf-8")
    print(output)
    print(subtitles)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
