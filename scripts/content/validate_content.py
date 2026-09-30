#!/usr/bin/env python3
"""Validate a Content Generator record and reject loose or invalid release files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = (ROOT / "content").resolve()
REQUIRED = {"id", "name", "brand", "topic", "locales", "generatorProfile", "status"}
ALLOWED_ROOT_FILES = {".DS_Store", "content.json", "project.json", "deliverables.json", "brief.md", "README.md", "pipeline.json"}
ALLOWED_ROOT_DIRS = {"source", "storyboard", "shots", "production", "edit", "drafts", "releases", "finals", "archive", "references", "previews", "requests", "costs", "assets", "dubbing", "estimates"}


def content_path(value: str) -> Path:
    candidate = (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if candidate.parent != CONTENT_ROOT:
        raise argparse.ArgumentTypeError("Content must be a direct child of content/.")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content", type=content_path)
    args = parser.parse_args()
    errors: list[str] = []
    record_path = args.content / "content.json"
    if not record_path.is_file():
        # Legacy content stays readable while it is migrated; it is not silently called valid.
        print("LEGACY: missing content.json; run migration before creating new work.")
        return 0
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        errors.append(f"content.json is invalid JSON: {error}")
        record = {}
    missing = REQUIRED - set(record)
    if missing:
        errors.append("content.json missing: " + ", ".join(sorted(missing)))
    if record.get("id") != args.content.name:
        errors.append("content.json id must match its folder name")
    if not isinstance(record.get("locales"), list) or not record["locales"]:
        errors.append("content.json locales must be a non-empty list")
    legacy = record.get("migration", {}).get("sourceLayout") == "legacy"
    if not legacy:
        for entry in args.content.iterdir():
            if entry.is_file() and entry.name not in ALLOWED_ROOT_FILES:
                errors.append(f"loose root file: {entry.name}")
            if entry.is_dir() and entry.name not in ALLOWED_ROOT_DIRS:
                errors.append(f"unknown root folder: {entry.name}")
    if errors:
        print("INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    label = "VALID (legacy layout preserved)" if legacy else "VALID"
    print(f"{label}: {args.content.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
