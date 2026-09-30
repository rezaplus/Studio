#!/usr/bin/env python3
"""Prepare native-resolution, per-beat HeyGen Persian proofread sessions.

This produces editable provider subtitles first. It never upscales and never
renders final translations, so scripts can be checked before the paid render.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("heygen")


def env() -> dict[str, str]:
    result = dict(os.environ)
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for raw in dotenv.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, raw_value = line.split("=", 1)
                result.setdefault(key.strip(), raw_value.strip().strip('"').strip("'"))
    return result


def call(arguments: list[str], environment: dict[str, str]) -> dict:
    result = subprocess.run(["heygen", *arguments], cwd=ROOT, env=environment, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def asset_id(response: dict) -> str:
    value = response.get("data", {}).get("asset_id")
    if not isinstance(value, str):
        raise RuntimeError("HeyGen upload returned no asset ID")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    workspace = plan_path.parent
    source = (ROOT / plan["sourceVideo"]).resolve()
    environment = env()
    records: list[dict] = []

    for segment in plan["segments"]:
        clip = workspace / f"{segment['id']}.source.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(segment["start"]), "-to", str(segment["end"]),
            "-i", str(source), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(clip),
        ], cwd=ROOT, check=True)
        upload = call(["asset", "create", "--file", str(clip)], environment)
        payload = {
            "title": f"hair-salon-fa-native-v3-{segment['id']}",
            "video": {"type": "asset_id", "asset_id": asset_id(upload)},
            "output_languages": [plan["language"]],
            "mode": "precision",
            "speaker_num": segment["speakerCount"],
            "enable_speech_enhancement": True,
            "enable_video_stretching": True,
            "keep_the_same_format": True,
        }
        response = call(["video-translate", "proofreads", "create", "--data", json.dumps(payload)], environment)
        proofreads = response.get("data", {}).get("proofread_ids", [])
        if not proofreads:
            raise RuntimeError(f"HeyGen created no proofread for {segment['id']}")
        records.append({
            **segment,
            "sourceClip": str(clip.relative_to(ROOT)),
            "proofreadId": proofreads[0],
            "srt": str((workspace / f"{segment['id']}.fa.srt").relative_to(ROOT)),
        })
        print(f"Prepared {segment['id']}", flush=True)

    (workspace / "sessions.json").write_text(json.dumps({"sourceVideo": plan["sourceVideo"], "segments": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
