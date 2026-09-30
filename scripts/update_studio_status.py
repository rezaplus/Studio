#!/usr/bin/env python3
"""Promote a registered Studio delivery without moving its immutable bundle."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = (ROOT / "content").resolve()
STATUSES = {"draft", "review", "approved", "archived"}


def project_path(value: str) -> Path:
    candidate = Path(value)
    project = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    if project.parent != CONTENT_ROOT or not project.is_dir():
        raise argparse.ArgumentTypeError("Content must be an existing direct child of content/.")
    return project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=project_path)
    parser.add_argument("release_id")
    parser.add_argument("status", choices=sorted(STATUSES))
    parser.add_argument("--make-current", action="store_true")
    parser.add_argument("--editorial-approval", action="store_true", help="Required when setting approved.")
    args = parser.parse_args()
    if not re.fullmatch(r"[\w-]+", args.release_id):
        parser.error("release_id must contain only letters, numbers, _ or -.")
    if args.status == "approved" and not args.editorial_approval:
        parser.error("approved requires --editorial-approval.")

    manifest_path = args.project / "deliverables.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("releases"), list):
        raise RuntimeError("Existing deliverables.json is not schemaVersion 1.")
    release = next((item for item in manifest["releases"] if item.get("id") == args.release_id), None)
    if not release:
        raise RuntimeError(f"Unknown Studio delivery: {args.release_id}")
    release["status"] = args.status
    if args.make_current:
        manifest.setdefault("current", {})[release["language"]] = release["id"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {release['id']} to {args.status}")


if __name__ == "__main__":
    main()
