#!/usr/bin/env python3
"""Upload a local image reference to Higgsfield and print its public HTTPS URL."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from generate_video import ROOT, api_request, load_dotenv, now_slug, save_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Local reference image, preferably stored in input/")
    parser.add_argument("--content-type", help="Override MIME type when it cannot be detected")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    source = args.file.expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"Reference file not found: {source}")
    content_type = args.content_type or mimetypes.guess_type(source.name)[0]
    if not content_type or not content_type.startswith("image/"):
        raise RuntimeError("Use a recognised image file (JPEG, PNG, WebP, etc.) or provide --content-type image/<type>.")

    ticket = api_request("https://api.higgsfield.ai/files/generate-upload-url", method="POST", data={"content_type": content_type})
    upload_url = ticket.get("upload_url")
    public_url = ticket.get("public_url")
    upload_headers = ticket.get("upload_headers") or {}
    for url, label in ((upload_url, "upload_url"), (public_url, "public_url")):
        parsed = urlparse(url) if isinstance(url, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.hostname:
            raise RuntimeError(f"Higgsfield upload ticket has an invalid {label}.")
    if not isinstance(upload_headers, dict):
        raise RuntimeError("Higgsfield upload ticket has invalid upload_headers.")

    headers = {str(key): str(value) for key, value in upload_headers.items()}
    headers.setdefault("Content-Type", content_type)
    headers.setdefault("User-Agent", "Higgsfield-Reels-Workspace/1.0")
    try:
        payload = source.read_bytes()
        with urlopen(Request(upload_url, data=payload, method="PUT", headers=headers), timeout=180) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Reference upload returned HTTP {response.status}.")
    except HTTPError as error:
        raise RuntimeError(f"Reference upload returned HTTP {error.code}: {error.read().decode('utf-8', errors='replace')}") from error
    except (URLError, OSError) as error:
        raise RuntimeError(f"Could not upload reference image: {error}") from error

    record = {
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": source.name,
        "content_type": content_type,
        "public_url": public_url,
    }
    saved = save_json("uploads", f"{now_slug()}-reference.json", record)
    print(f"Public image URL: {public_url}")
    print(f"Saved upload record: {saved.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
