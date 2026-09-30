#!/usr/bin/env python3
"""Get Higgsfield's cost estimate for a video request without submitting it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generate_video import ROOT, api_request, has_placeholder, load_dotenv, now_slug, save_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default="requests/default-text-to-video.json", help="JSON payload relative to project root")
    parser.add_argument("--prompt", help="Replace prompt in the selected JSON payload")
    parser.add_argument("--model", help="Override model path")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    request_path = (ROOT / args.request).resolve()
    if ROOT not in request_path.parents or not request_path.is_file():
        raise RuntimeError("--request must name an existing JSON file inside this project.")
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Request JSON must contain an object.")
    if args.prompt:
        payload["prompt"] = args.prompt
    if not payload.get("prompt"):
        raise RuntimeError("A non-empty prompt is required.")
    if has_placeholder(payload):
        raise RuntimeError("Replace every REPLACE_WITH_... value with a real public HTTPS URL before estimating.")

    import os
    base_url = os.environ.get("HF_API_BASE_URL", "https://api.higgsfield.ai").rstrip("/")
    model = (args.model or os.environ.get("HF_MODEL", "bytedance/seedance-2.0/text-to-video")).strip("/")
    estimate = api_request(f"{base_url}/estimate/{model}", method="POST", data=payload)
    saved = save_json("estimates", f"{now_slug()}-estimate.json", {"model": model, "input": payload, "estimate": estimate})
    print(json.dumps(estimate, ensure_ascii=False, indent=2))
    print(f"Saved estimate: {saved.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
