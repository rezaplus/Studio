#!/usr/bin/env python3
"""Turn videos dropped in input/videos/ into Content records, automatically.

For each video: derive a name and topic, scaffold the content folder with
new_content.py, move the video in with import_video.py, and write a probe
summary to the brief. Nothing here calls a provider or costs money.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import workspace  # noqa: E402
INBOX = ROOT / "input" / "videos"
CONTENT_ROOT = ROOT / "content"
SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
GENERIC = re.compile(r"^(img|vid|mov|video|screen-?recording|clip|untitled|whatsapp|pxl|dji|\d)[-_ 0-9a-z]*$", re.I)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def derive(path: Path) -> tuple[str, str]:
    """Return (name, topic) from the file name; generic names become unsorted."""
    slug = slugify(path.stem)
    if not slug:  # e.g. a Persian-only file name
        slug = "video-" + hashlib.sha1(path.stem.encode()).hexdigest()[:6]
    generic = bool(GENERIC.match(path.stem)) or slug.startswith("video-")
    return slug, ("unsorted" if generic else slug)


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    data = json.loads(out.stdout or "{}")
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "width": video.get("width"), "height": video.get("height"),
        "duration": round(float(data.get("format", {}).get("duration", 0) or 0), 2),
        "hasAudio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


def unique_name(name: str) -> str:
    candidate, n = name, 2
    while list(CONTENT_ROOT.glob(f"cnt-*-{candidate}")):
        candidate, n = f"{name}-{n}", n + 1
    return candidate


def ingest(video: Path, args: argparse.Namespace) -> None:
    name, topic = derive(video)
    name = slugify(args.name) if args.name else name
    topic = slugify(args.topic) if args.topic else topic
    info = probe(video)
    vertical = bool(info) and info["height"] and info["height"] > info["width"]
    if args.dry_run:
        print(f"[dry-run] {video.name} -> name={name} topic={topic} probe={info}")
        return
    name = unique_name(name)
    created = subprocess.run(
        [sys.executable, str(ROOT / "scripts/content/new_content.py"), "--name", name,
         "--brand", args.brand, "--topic", topic, "--locales", args.locales],
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/content/import_video.py"), "--content", created,
         "--video", str(video)], check=True, capture_output=True)
    brief = ROOT / created / "brief.md"
    note = (f"# Brief\n\nSource video: `{video.name}` "
            f"({info.get('width')}x{info.get('height')}, {info.get('duration')}s, "
            f"audio: {info.get('hasAudio')}){'' if vertical else ' - NOT 9:16, reframe in edit'}.\n\n"
            f"Topic: {topic}" + (" (auto: filename was generic; ask the agent/user to set a real topic)" if topic == "unsorted" else "") + "\n")
    brief.write_text(note, encoding="utf-8")
    print(f"{video.name} -> {created}  (topic: {topic})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos", nargs="*", help="Files inside input/videos/. Default: every video there.")
    parser.add_argument("--name", help="Override the derived name (single video only).")
    parser.add_argument("--topic", help="Override the derived topic (single video only).")
    parser.add_argument("--brand", default=workspace.default_brand())
    parser.add_argument("--locales", default=workspace.default_locales())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    files = [Path(v) if Path(v).is_absolute() else ROOT / v for v in args.videos] or \
        sorted(p for p in INBOX.iterdir() if p.suffix.lower() in SUFFIXES)
    if not files:
        print("No videos in input/videos/. Drop a .mp4/.mov there first.")
        return 1
    if (args.name or args.topic) and len(files) > 1:
        parser.error("--name/--topic apply to a single video.")
    for video in files:
        ingest(video.resolve(), args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
