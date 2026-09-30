#!/usr/bin/env python3
"""Register a local Reel draft or release in its project-local Studio bundle.

This script never publishes externally. It copies an existing local render into
content/<content-id>/drafts/<language>/vN/ for editorial drafts, or
content/<content-id>/releases/<language>/vN/ for final delivery bundles. Studio
discovers either registered state on its next refresh.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = (ROOT / "content").resolve()
VALID_STATUSES = {"draft", "review", "approved", "archived"}


def project_path(value: str) -> Path:
    candidate = Path(value)
    project = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    if project.parent != CONTENT_ROOT or not project.is_dir():
        raise argparse.ArgumentTypeError("Content must be an existing direct child of content/.")
    return project


def video_path(value: str) -> Path:
    candidate = Path(value)
    video = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    if not video.is_file() or video.suffix.lower() not in {".mp4", ".mov", ".webm"}:
        raise argparse.ArgumentTypeError("Video must be an existing .mp4, .mov, or .webm file.")
    return video


def load_manifest(project: Path, title: str) -> dict:
    manifest_path = project / "deliverables.json"
    if not manifest_path.exists():
        return {"schemaVersion": 1, "title": title, "current": {}, "releases": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("releases"), list):
        raise RuntimeError("Existing deliverables.json is not schemaVersion 1.")
    manifest.setdefault("title", title)
    manifest.setdefault("current", {})
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a local Reel render in the read-only Studio gallery.")
    parser.add_argument("project", type=project_path, help="Content directory, e.g. content/cnt-20260929-phone-experiment")
    parser.add_argument("video", type=video_path, help="Existing local rendered video")
    parser.add_argument("--language", default="en", help="Release language (default: en)")
    parser.add_argument("--caption", default="", help="Optional post caption saved alongside this bundle")
    parser.add_argument("--subtitles", type=Path, help="Optional local .srt or .vtt copied into this release")
    parser.add_argument("--label", default="Editorial review", help="Human-readable version label")
    parser.add_argument("--notes", default="", help="Review note shown in Studio")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES), default="draft")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z]{2}(?:-[A-Za-z0-9]+)*", args.language):
        parser.error("--language must look like en, fa, tr, ar, or en-US.")

    meta_path = args.project / "project.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        meta = {}
    title = meta.get("title") or args.project.name.replace("-", " ").title()
    manifest = load_manifest(args.project, title)

    versions = [r.get("version", 0) for r in manifest["releases"] if r.get("language") == args.language]
    version = max((v for v in versions if isinstance(v, int)), default=0) + 1
    release_id = f"{args.language}-v{version}"
    bundle_root = "drafts" if args.status == "draft" else "releases"
    target_dir = args.project / bundle_root / args.language / f"v{version:03d}"
    if target_dir.exists():
        raise RuntimeError(f"Refusing to overwrite existing immutable bundle: {target_dir}")
    target_dir.mkdir(parents=True)
    target_video = target_dir / "video.mp4"
    shutil.copy2(args.video, target_video)
    caption_target = None
    if args.caption.strip():
        caption_target = target_dir / "caption.txt"
        caption_target.write_text(args.caption.strip() + "\n", encoding="utf-8")
    subtitle_target = None
    if args.subtitles:
        subtitle_source = args.subtitles.resolve()
        if not subtitle_source.is_file() or subtitle_source.suffix.lower() not in {".srt", ".vtt"}:
            parser.error("--subtitles must be an existing .srt or .vtt file.")
        subtitle_target = target_dir / f"subtitles{subtitle_source.suffix.lower()}"
        shutil.copy2(subtitle_source, subtitle_target)

    release = {
        "id": release_id,
        "language": args.language,
        "version": version,
        "status": args.status,
        "label": args.label,
        "video": target_video.relative_to(args.project).as_posix(),
        "notes": args.notes,
    }
    if caption_target:
        release["caption"] = caption_target.relative_to(args.project).as_posix()
    if subtitle_target:
        release["subtitles"] = subtitle_target.relative_to(args.project).as_posix()
    manifest["releases"].append(release)
    manifest["current"][args.language] = release_id
    (args.project / "deliverables.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Registered {release_id} ({args.status})")
    print(f"Video: {target_video.relative_to(ROOT)}")
    print(f"Manifest: {(args.project / 'deliverables.json').relative_to(ROOT)}")
    print("Refresh Studio to see the new release.")


if __name__ == "__main__":
    main()
