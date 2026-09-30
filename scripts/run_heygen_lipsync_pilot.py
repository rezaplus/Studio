#!/usr/bin/env python3
"""Run one short, review-first HeyGen Precision Proofread lip-sync pilot.

The pilot intentionally leaves output at the source resolution. Upscaling is a
separate finishing decision after a human approves the mouth motion.
"""

from __future__ import annotations

import argparse
import json
import os
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


def environment() -> dict[str, str]:
    result = dict(os.environ)
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for raw in dotenv.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return result


def heygen(arguments: list[str], env: dict[str, str]) -> dict:
    completed = subprocess.run(
        ["heygen", *arguments], cwd=ROOT, env=env, text=True, capture_output=True
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def value(data: object, key: str) -> str | None:
    if isinstance(data, dict):
        candidate = data.get(key)
        if isinstance(candidate, str):
            return candidate
        for child in data.values():
            found = value(child, key)
            if found:
                return found
    if isinstance(data, list):
        for child in data:
            found = value(child, key)
            if found:
                return found
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output = config_path.parent
    source = (ROOT / config["sourceClip"]).resolve()
    env = environment()

    uploaded = heygen(["asset", "create", "--file", str(source)], env)
    asset_id = value(uploaded, "asset_id")
    if not asset_id:
        raise RuntimeError("HeyGen did not return an upload asset ID")

    payload = {
        "title": "hair-salon-fa-native-480-hook-pilot",
        "video": {"type": "asset_id", "asset_id": asset_id},
        "output_languages": [config["language"]],
        "mode": "precision",
        "speaker_num": config["speakerCount"],
        "enable_speech_enhancement": True,
        "enable_video_stretching": True,
        "keep_the_same_format": True,
    }
    created = heygen(
        ["video-translate", "proofreads", "create", "--data", json.dumps(payload)], env
    )
    proofread_ids = created.get("data", {}).get("proofread_ids", [])
    if not proofread_ids:
        raise RuntimeError("HeyGen did not return a proofread ID")
    proofread_id = proofread_ids[0]
    record = {"assetId": asset_id, "proofreadId": proofread_id, "config": config}
    (output / "job.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Proofread prepared; waiting for editable Persian script…", flush=True)

    for _ in range(72):
        status = heygen(["video-translate", "proofreads", "get", proofread_id], env)
        data = status.get("data", status)
        if data.get("status") == "completed":
            break
        if data.get("status") == "failed":
            raise RuntimeError(data.get("failure_message") or "HeyGen proofread failed")
        time.sleep(10)
    else:
        raise TimeoutError("HeyGen proofread did not complete within 12 minutes")

    srt_info = heygen(["video-translate", "proofreads", "srt", "get", proofread_id], env)
    srt_url = srt_info.get("data", {}).get("srt_url")
    if not isinstance(srt_url, str):
        raise RuntimeError("HeyGen did not return the target SRT")
    srt_path = output / "hook.fa.srt"
    with urllib.request.urlopen(srt_url) as response:
        srt_path.write_bytes(response.read())

    final = heygen(["video-translate", "proofreads", "generate", proofread_id, "--data", "{}"], env)
    translation_id = value(final, "video_translation_id") or value(final, "id")
    if not translation_id:
        raise RuntimeError("HeyGen did not return a render ID")
    record["translationId"] = translation_id
    (output / "job.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Lip-sync rendering…", flush=True)

    for _ in range(72):
        status = heygen(["video-translate", "get", translation_id], env)
        data = status.get("data", status)
        if data.get("status") == "completed":
            break
        if data.get("status") == "failed":
            raise RuntimeError(data.get("failure_message") or "HeyGen render failed")
        time.sleep(10)
    else:
        raise TimeoutError("HeyGen render did not complete within 12 minutes")
    video_url = value(data, "video_url")
    if not video_url:
        raise RuntimeError("HeyGen did not return the rendered video")
    target = output / "hook.fa.mp4"
    with urllib.request.urlopen(video_url) as response:
        target.write_bytes(response.read())
    print(target)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
