#!/usr/bin/env python3
"""Move one staged input video into a Content record when editing begins."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = (ROOT / "content").resolve()
VIDEO_INBOX = (ROOT / "input" / "videos").resolve()
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}


def content_path(value: str) -> Path:
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    if resolved.parent != CONTENT_ROOT or not resolved.is_dir():
        raise argparse.ArgumentTypeError("--content must be an existing direct child of content/.")
    return resolved


def inbox_video(value: str) -> Path:
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    if VIDEO_INBOX not in resolved.parents or not resolved.is_file():
        raise argparse.ArgumentTypeError("--video must be a file inside input/videos/.")
    if resolved.suffix.lower() not in VIDEO_SUFFIXES:
        raise argparse.ArgumentTypeError("--video must be an MP4, MOV, M4V, or WebM file.")
    return resolved


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", required=True, type=content_path)
    parser.add_argument("--video", required=True, type=inbox_video)
    args = parser.parse_args()

    target_dir = args.content / "source" / "video"
    target = target_dir / args.video.name
    if target.exists():
        raise RuntimeError(f"Refusing to overwrite existing source video: {target.relative_to(ROOT)}")
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256(args.video)
    byte_count = args.video.stat().st_size
    shutil.move(str(args.video), str(target))
    record = {
        "schemaVersion": 1,
        "contentId": args.content.name,
        "event": "source-video-imported-for-editing",
        "source": args.video.relative_to(ROOT).as_posix(),
        "target": target.relative_to(ROOT).as_posix(),
        "bytes": byte_count,
        "sha256": digest,
        "movedAt": datetime.now(timezone.utc).isoformat(),
    }
    (target_dir / f"{target.stem}.import.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Moved: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
