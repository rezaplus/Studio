#!/usr/bin/env python3
"""Preview or estimate every Higgsfield shot in a Reel project without generating video."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from generate_video import ROOT, api_request, has_placeholder, load_dotenv


def extract_number(value: object, keys: set[str]) -> float | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in keys:
                try:
                    return float(item)
                except (TypeError, ValueError):
                    pass
        for item in value.values():
            found = extract_number(item, keys)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = extract_number(item, keys)
            if found is not None:
                return found
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="Content directory, e.g. content/cnt-20260929-phone-experiment")
    parser.add_argument("--estimate", action="store_true", help="Call the non-billable estimate endpoint for ready Higgsfield shots")
    args = parser.parse_args()
    project = args.project.resolve()
    manifest_path = project / "project.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Missing project manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_url = None
    if args.estimate:
        load_dotenv(ROOT / ".env")
        import os
        base_url = os.environ.get("HF_API_BASE_URL", "https://api.higgsfield.ai").rstrip("/")

    rows, total = [], 0.0
    for shot in manifest["shots"]:
        if shot["production"] != "higgsfield":
            rows.append({"id": shot["id"], "mode": shot["production"], "status": "no Higgsfield cost"})
            continue
        request_path = project / shot["request"]
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        if has_placeholder(payload):
            rows.append({"id": shot["id"], "mode": "higgsfield", "status": "needs uploaded reference URL"})
            continue
        if not args.estimate:
            rows.append({"id": shot["id"], "mode": "higgsfield", "status": "ready; run with --estimate", "model": shot["model"]})
            continue
        response = api_request(f"{base_url}/estimate/{shot['model']}", method="POST", data=payload)
        usd = extract_number(response, {"usd", "cost_usd", "price_usd"})
        if usd is not None:
            total += usd
        rows.append({"id": shot["id"], "mode": "higgsfield", "status": "estimated", "model": shot["model"], "usd": usd, "response": response})

    result = {"project": manifest["slug"], "created_at": datetime.now(timezone.utc).isoformat(), "estimated": args.estimate, "total_usd": total if args.estimate else None, "shots": rows}
    output_dir = project / "estimates"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-project-estimate.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        price = f" — ${row['usd']:.4f}" if row.get("usd") is not None else ""
        print(f"{row['id']}: {row['status']}{price}")
    if args.estimate:
        print(f"Total exact pre-submit estimate: ${total:.4f}")
    print(f"Saved: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
