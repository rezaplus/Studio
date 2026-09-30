#!/usr/bin/env python3
"""Check an existing Higgsfield request without submitting another paid generation."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_video import ROOT, api_request, load_dotenv, save_json, status_from, video_url_from, now_slug  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_id")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    base_url = __import__("os").environ.get("HF_API_BASE_URL", "https://api.higgsfield.ai").rstrip("/")
    result = api_request(f"{base_url}/requests/{args.request_id}/status")
    target = save_json("status", f"{now_slug()}-{args.request_id}.json", result)
    print(f"Status: {status_from(result)}")
    print(f"Saved: {target.relative_to(ROOT)}")
    url = video_url_from(result)
    if url:
        print(f"Video URL: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
