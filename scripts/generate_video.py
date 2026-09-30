#!/usr/bin/env python3
"""Submit a Higgsfield generation, optionally wait, then save its video and metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen, urlretrieve

ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("higgsfield")
RUNTIME_ROOT = ROOT / "runtime" / "higgsfield"


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without replacing values already in the shell."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_json(directory: str, name: str, payload: object) -> Path:
    target = RUNTIME_ROOT / directory / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def api_request(url: str, method: str = "GET", data: dict | None = None) -> dict:
    key_id = os.environ.get("HF_API_KEY_ID")
    key_secret = os.environ.get("HF_API_KEY_SECRET")
    if not key_id or not key_secret or key_id == "your_key_id":
        raise RuntimeError("HF_API_KEY_ID and HF_API_KEY_SECRET must be set in .env.")
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(url, data=body, method=method)
    request.add_header("Authorization", f"Key {key_id}:{key_secret}")
    request.add_header("Accept", "application/json")
    # Cloudflare rejects urllib's default Python user agent on this API. Use a
    # stable, descriptive client identifier for every authenticated request.
    request.add_header("User-Agent", "Higgsfield-Reels-Workspace/1.0")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Higgsfield returned HTTP {error.code}: {details}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach Higgsfield: {error.reason}") from error
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Expected JSON from Higgsfield, received: {raw[:500]}") from error
    if not isinstance(result, dict):
        raise RuntimeError("Expected a JSON object from Higgsfield.")
    return result


def find_value(data: object, names: set[str]) -> object | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in names and value not in (None, ""):
                return value
        for value in data.values():
            found = find_value(value, names)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_value(value, names)
            if found is not None:
                return found
    return None


def request_id_from(data: dict) -> str | None:
    value = find_value(data, {"request_id", "requestid"})
    if value is None and isinstance(data.get("id"), str):
        value = data["id"]
    return str(value) if value is not None else None


def status_from(data: dict) -> str:
    value = find_value(data, {"status", "state"})
    return str(value).lower() if value is not None else "unknown"


def video_url_from(data: object) -> str | None:
    named = find_value(data, {"video", "video_url", "url", "download_url"})
    if isinstance(named, str) and named.startswith(("http://", "https://")):
        return named
    if isinstance(named, dict):
        nested = find_value(named, {"url", "download_url", "video_url"})
        if isinstance(nested, str) and nested.startswith(("http://", "https://")):
            return nested
    serialized = json.dumps(data)
    match = re.search(r'https?://[^\"\\ ]+?\.(?:mp4|mov|webm)(?:\?[^\"\\ ]*)?', serialized, re.I)
    return match.group(0) if match else None


def has_placeholder(value: object) -> bool:
    if isinstance(value, str):
        return "REPLACE_WITH_" in value
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    return False


def poll(base_url: str, request_id: str, interval: int, max_wait: int) -> dict:
    deadline = time.monotonic() + max_wait
    terminal_success = {"completed", "complete", "succeeded", "success", "done"}
    terminal_error = {"failed", "error", "cancelled", "canceled", "rejected"}
    while True:
        result = api_request(f"{base_url}/requests/{request_id}/status")
        status = status_from(result)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {request_id}: {status}", flush=True)
        if status in terminal_success:
            return result
        if status in terminal_error:
            raise RuntimeError(f"Request {request_id} ended with status '{status}'.")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for {request_id}. Check it later with request_status.py.")
        time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default="requests/default-text-to-video.json", help="JSON request payload relative to project root; the default is a 9:16 Instagram Reel")
    parser.add_argument("--prompt", help="Replace prompt in the selected request JSON")
    parser.add_argument("--model", help="Override model path, e.g. bytedance/seedance-2.0/text-to-video")
    parser.add_argument("--wait", action="store_true", help="Poll until completion and download the generated video")
    parser.add_argument("--interval", type=int, help="Polling interval in seconds")
    parser.add_argument("--max-wait", type=int, help="Maximum polling time in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    payload_path = (ROOT / args.request).resolve()
    if ROOT not in payload_path.parents or not payload_path.is_file():
        raise RuntimeError("--request must name an existing JSON file inside this project.")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Request JSON must contain an object.")
    if args.prompt:
        payload["prompt"] = args.prompt
    if not payload.get("prompt"):
        raise RuntimeError("A non-empty prompt is required.")
    if has_placeholder(payload):
        raise RuntimeError("Replace every REPLACE_WITH_... value with a real public HTTPS URL before submitting.")

    base_url = os.environ.get("HF_API_BASE_URL", "https://api.higgsfield.ai").rstrip("/")
    model = args.model or os.environ.get("HF_MODEL", "bytedance/seedance-2.0/text-to-video")
    model = model.strip("/")
    submission = api_request(f"{base_url}/{model}", method="POST", data=payload)
    request_id = request_id_from(submission)
    stamp = now_slug()
    saved_request = save_json("requests", f"{stamp}-submission.json", {"model": model, "input": payload, "response": submission})
    print(f"Submission saved: {saved_request.relative_to(ROOT)}")
    if not request_id:
        raise RuntimeError("No request ID found in the API response; inspect the saved submission file.")
    print(f"Request ID: {request_id}")
    if not args.wait:
        print(f"Check later: python3 scripts/request_status.py {request_id}")
        return 0

    status = poll(base_url, request_id, args.interval or int(os.environ.get("HF_POLL_INTERVAL_SECONDS", "8")), args.max_wait or int(os.environ.get("HF_MAX_WAIT_SECONDS", "900")))
    saved_status = save_json("status", f"{stamp}-{request_id}.json", status)
    video_url = video_url_from(status)
    if not video_url:
        raise RuntimeError(f"Generation completed but no video URL was found. Inspect {saved_status.relative_to(ROOT)}")
    output = ROOT / "runtime" / "media" / "higgsfield" / f"{stamp}-{request_id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading video to {output.relative_to(ROOT)} …", flush=True)
    urlretrieve(video_url, output)
    print(f"Completed: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        failure = {"time": datetime.now(timezone.utc).isoformat(), "error": str(error)}
        path = save_json("errors", f"{now_slug()}-error.json", failure)
        print(f"Error: {error}\nSaved diagnostic: {path.relative_to(ROOT)}", file=sys.stderr)
        raise SystemExit(1)
