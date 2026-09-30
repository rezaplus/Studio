#!/usr/bin/env python3
"""Preview or safely submit a HeyGen V3 video-translation job.

The command accepts a local MP4 (uploaded as a private HeyGen asset) or an
already public HTTPS URL.  It is deliberately dry-run by default: sending a
translation requires both --submit and the explicit paid-operation flag.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("heygen")
API_BASE = "https://api.heygen.com/v3"
TERMINAL = {"completed", "failed"}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip("\"'")


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_json(folder: str, filename: str, data: object) -> Path:
    path = ROOT / "runtime" / "heygen" / folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def api_key() -> str:
    value = os.environ.get("HEYGEN_API_KEY", "").strip()
    if not value or value == "your_heygen_api_key":
        raise RuntimeError("Set HEYGEN_API_KEY in .env before submitting or reading API data.")
    return value


def request_json(path: str, method: str = "GET", payload: dict | None = None,
                 idempotency_key: str | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(f"{API_BASE}{path}", data=body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("X-Api-Key", api_key())
    req.add_header("User-Agent", "Studio-HeyGen-Dubbing/1.0")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if idempotency_key:
        req.add_header("Idempotency-Key", idempotency_key)
    try:
        with urlopen(req, timeout=90) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HeyGen returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach HeyGen: {error.reason}") from error
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"HeyGen returned non-JSON data: {raw[:500]}") from error
    if not isinstance(data, dict):
        raise RuntimeError("HeyGen returned an unexpected JSON response.")
    if data.get("error"):
        raise RuntimeError(f"HeyGen error: {data['error']}")
    return data


def upload_local_video(video_path: Path) -> str:
    """Use direct upload, avoiding a 32 MB proxy limit and public hosting."""
    content_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
    initial = request_json(
        "/assets/direct-uploads",
        method="POST",
        payload={
            "filename": video_path.name,
            "content_type": content_type,
            "size_bytes": video_path.stat().st_size,
        },
        idempotency_key=str(uuid.uuid4()),
    )
    data = initial.get("data", {})
    asset_id = data.get("asset_id")
    upload_url = data.get("upload_url")
    upload_headers = data.get("upload_headers")
    if not isinstance(asset_id, str) or not isinstance(upload_url, str) or not isinstance(upload_headers, dict):
        raise RuntimeError("HeyGen did not return a usable direct-upload response.")

    put = Request(upload_url, data=video_path.read_bytes(), method="PUT")
    for key, value in upload_headers.items():
        put.add_header(str(key), str(value))
    try:
        with urlopen(put, timeout=300) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"HeyGen asset upload returned HTTP {response.status}.")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HeyGen asset upload failed with HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not upload the source video to HeyGen: {error.reason}") from error

    complete = request_json(f"/assets/{asset_id}/complete", method="POST", payload={})
    final_asset_id = complete.get("data", {}).get("asset_id", asset_id)
    if not isinstance(final_asset_id, str):
        raise RuntimeError("HeyGen did not return an asset ID after completing the upload.")
    return final_asset_id


def local_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"Source video does not exist: {value}")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", help="Local MP4/MOV/WebM path. Uploads privately to HeyGen only with --submit.")
    source.add_argument("--source-url", help="Public HTTPS source video URL.")
    parser.add_argument("--request", default="requests/heygen-video-translation.json", help="Secret-free request JSON relative to project root.")
    parser.add_argument("--languages", nargs="+", help="Override output_languages using names returned by --list-languages.")
    parser.add_argument("--mode", choices=("speed", "precision"), help="Override translation mode.")
    parser.add_argument("--list-languages", action="store_true", help="List HeyGen's currently available target-language names; no generation charge.")
    parser.add_argument("--submit", action="store_true", help="Upload (when local) and submit the paid translation request.")
    parser.add_argument("--yes-i-understand-this-is-a-paid-request", action="store_true", dest="paid_confirmation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    if args.list_languages:
        result = request_json("/video-translations/languages")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    request_path = (ROOT / args.request).resolve()
    if ROOT not in request_path.parents or not request_path.is_file():
        raise RuntimeError("--request must point to an existing JSON file inside this project.")
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Request JSON must contain an object.")
    if args.languages:
        payload["output_languages"] = args.languages
    if args.mode:
        payload["mode"] = args.mode
    languages = payload.get("output_languages")
    if not isinstance(languages, list) or not languages or not all(isinstance(x, str) and x.strip() for x in languages):
        raise RuntimeError("Request must include a non-empty output_languages list.")
    if payload.get("mode", "speed") not in {"speed", "precision"}:
        raise RuntimeError("mode must be speed or precision.")

    if args.source_url:
        if not args.source_url.startswith("https://"):
            raise RuntimeError("--source-url must be an HTTPS URL accessible without a login.")
        source_description = {"type": "url", "url": args.source_url}
    else:
        source_file = local_path(args.source)
        source_description = {"type": "local_file", "path": str(source_file), "bytes": source_file.stat().st_size}

    preview = {"source": source_description, "translation": payload, "estimated_jobs": len(languages)}
    print("Prepared HeyGen translation request (not submitted):")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if not args.submit:
        print("\nDry run only. To submit a paid job, add --submit --yes-i-understand-this-is-a-paid-request.")
        return 0
    if not args.paid_confirmation:
        raise RuntimeError("Paid submission blocked. Add --yes-i-understand-this-is-a-paid-request after reviewing the request.")

    if args.source_url:
        payload["video"] = {"type": "url", "url": args.source_url}
    else:
        asset_id = upload_local_video(source_file)
        payload["video"] = {"type": "asset_id", "asset_id": asset_id}
    idempotency_key = str(uuid.uuid4())
    response = request_json("/video-translations", method="POST", payload=payload, idempotency_key=idempotency_key)
    record = {"idempotency_key": idempotency_key, "input": payload, "response": response}
    saved = save_json("requests", f"{timestamp()}-translation.json", record)
    ids = response.get("data", {}).get("video_translation_ids", [])
    print(f"Submitted {len(ids)} translation job(s). Record: {saved.relative_to(ROOT)}")
    for job_id in ids:
        print(f"Status: python3 scripts/heygen_dub_status.py {job_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
