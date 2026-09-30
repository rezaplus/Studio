#!/usr/bin/env python3
"""Download target-language SRTs from completed HeyGen Proofread sessions.

This is intentionally read-only with respect to HeyGen: it uses the HeyGen CLI
only to retrieve the provider SRT URL, then saves the returned subtitle file
beside the project job records for editorial review.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("heygen")


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        return env
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    env = load_env()
    for segment in manifest["segments"]:
        result = subprocess.run(
            ["heygen", "video-translate", "proofreads", "srt", "get", segment["proofreadId"]],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        response = json.loads(result.stdout)
        url = response.get("data", {}).get("srt_url")
        if not isinstance(url, str):
            raise RuntimeError(f"No target SRT URL for {segment['id']}")
        target = Path(segment["srt"])
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url) as source:
            target.write_bytes(source.read())
        print(f"Downloaded {segment['id']} -> {target}")


if __name__ == "__main__":
    main()
