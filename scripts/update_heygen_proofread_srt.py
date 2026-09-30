#!/usr/bin/env python3
"""Upload editorial corrections to one completed HeyGen Proofread SRT."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("heygen")


def environment() -> dict[str, str]:
    env = dict(os.environ)
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def run(args: list[str], env: dict[str, str]) -> dict:
    result = subprocess.run(args, cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("proofread_id")
    parser.add_argument("srt", type=Path)
    args = parser.parse_args()
    srt = args.srt.resolve()
    if not srt.is_file() or srt.suffix.lower() != ".srt":
        parser.error("srt must be an existing .srt file")
    env = environment()
    upload = run(["heygen", "asset", "create", "--file", str(srt)], env)
    asset_id = upload.get("data", {}).get("asset_id")
    if not isinstance(asset_id, str):
        raise RuntimeError("HeyGen did not return an SRT asset ID")
    run(
        [
            "heygen", "video-translate", "proofreads", "srt", "update", args.proofread_id,
            "--data", json.dumps({"srt": {"type": "asset_id", "asset_id": asset_id}}),
        ],
        env,
    )
    print(f"Updated Proofread SRT: {args.proofread_id}")


if __name__ == "__main__":
    main()
