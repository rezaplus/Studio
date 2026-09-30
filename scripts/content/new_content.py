#!/usr/bin/env python3
"""Create one valid Content Generator workspace; never create loose folders."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import workspace  # noqa: E402
CONTENT_ROOT = ROOT / "content"


def slug(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise argparse.ArgumentTypeError("Use lowercase kebab-case, e.g. phone-experiment.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, type=slug)
    parser.add_argument("--brand", default=workspace.default_brand(), type=slug, help="Default from config/workspace.json")
    parser.add_argument("--topic", required=True, type=slug)
    parser.add_argument("--locales", default=workspace.default_locales(), help="Comma-separated locale codes, e.g. en,fa,tr,ar")
    parser.add_argument("--profile", default="reel-generator", type=slug)
    args = parser.parse_args()
    locales = [item.strip() for item in args.locales.split(",") if item.strip()]
    if not locales or any(not re.fullmatch(r"[a-z]{2}(?:-[A-Za-z0-9]+)*", item) for item in locales):
        parser.error("--locales must contain locale codes such as en, fa, tr, ar.")
    content_id = f"cnt-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{args.name}"
    base = CONTENT_ROOT / content_id
    if base.exists():
        raise RuntimeError(f"Content already exists: {base.relative_to(ROOT)}")
    for relative in ("source", "storyboard", "shots", "production", "edit", "drafts", "releases", "archive"):
        (base / relative).mkdir(parents=True, exist_ok=True)
    record = {
        "schemaVersion": 1,
        "id": content_id,
        "name": args.name,
        "brand": args.brand,
        "topic": args.topic,
        "formats": ["instagram-reel"],
        "locales": locales,
        "generatorProfile": args.profile,
        "status": "draft",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    (base / "content.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (base / "pipeline.json").write_text(json.dumps({
        "schemaVersion": 1,
        "contentId": content_id,
        "pipeline": "reel-main",
        "stages": {},
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (base / "brief.md").write_text("# Brief\n\n", encoding="utf-8")
    print(base.relative_to(ROOT))


if __name__ == "__main__":
    main()
