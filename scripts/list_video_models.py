#!/usr/bin/env python3
"""List currently available video models and public indicative prices from Higgsfield's live catalog."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_mode import require_api  # noqa: E402
require_api("higgsfield")
CATALOG_URL = "https://dash.higgsfield.ai/api/v2/catalog-models/?page_size=50"
CATALOG_HOST = "dash.higgsfield.ai"
CATALOG_PATH = "/api/v2/catalog-models/"


def fetch_json(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != CATALOG_HOST or parsed.path != CATALOG_PATH:
        raise RuntimeError("The catalog returned an unsafe or unexpected pagination URL.")
    try:
        with urlopen(Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Higgsfield-Reels-Workspace/1.0",
        }), timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read Higgsfield's live model catalog: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        raise RuntimeError("The catalog response schema changed (missing results).")
    return value


def load_catalog() -> list[dict]:
    entries: dict[str, dict] = {}
    current = CATALOG_URL
    seen: set[str] = set()
    while current:
        if current in seen or len(seen) >= 100:
            raise RuntimeError("Catalog pagination was repeated or exceeded its safety limit.")
        seen.add(current)
        page = fetch_json(current)
        for item in page["results"]:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                entries[item["id"]] = item
        current = page.get("next")
        if current is not None and not isinstance(current, str):
            raise RuntimeError("The catalog response schema changed (invalid next link).")
    return list(entries.values())


def model_row(item: dict) -> dict | None:
    if "video" not in item.get("output_types", []) or item.get("availability_state") != "available":
        return None
    pricing = item.get("pricing", {}).get("primary", {})
    company = item.get("company") or {}
    return {
        "slug": item.get("slug", ""),
        "name": item.get("title", "Unnamed model"),
        "provider": company.get("name", "Unknown"),
        "endpoint": item.get("default_mode_id") or "—",
        "price": pricing.get("amount"),
        "original_price": pricing.get("original_amount"),
        "currency": pricing.get("currency", "USD"),
        "unit": pricing.get("unit"),
        "qualifier": pricing.get("qualifier"),
        "discount_percent": pricing.get("discount_percentage"),
        "discount_expires_at": pricing.get("discount_expires_at"),
        "description": item.get("description", "").replace("\n", " "),
    }


def price_text(row: dict) -> str:
    if row["price"] is None:
        return "Price unavailable"
    prefix = "from " if row["qualifier"] == "from" else ""
    unit = f"/{row['unit']}" if row["unit"] else ""
    result = f"{prefix}${row['price']}{unit}"
    if row["original_price"] and row["original_price"] != row["price"]:
        result += f" (was ${row['original_price']}; {row['discount_percent']:g}% off)"
    return result


def save_snapshot(rows: list[dict]) -> Path:
    directory = ROOT / "runtime" / "higgsfield" / "catalogs"
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"{timestamp}-video-models.json"
    target.write_text(json.dumps({"retrieved_at": datetime.now(timezone.utc).isoformat(), "source": CATALOG_URL, "models": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", help="Filter by model name, provider, or description")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of a table")
    parser.add_argument("--no-save", action="store_true", help="Do not save a local catalog snapshot")
    args = parser.parse_args()

    rows = [row for item in load_catalog() if (row := model_row(item))]
    # The public catalog can temporarily expose duplicate family cards. Keep the
    # lowest public rate for a family, while exact pricing remains the estimate.
    unique: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["provider"], row["name"])
        current = unique.get(key)
        if current is None or (row["price"] is not None and (current["price"] is None or float(row["price"]) < float(current["price"]))):
            unique[key] = row
    rows = list(unique.values())
    if args.search:
        needle = args.search.lower()
        rows = [row for row in rows if needle in " ".join(str(row[key]) for key in ("name", "provider", "description")).lower()]
    rows.sort(key=lambda row: (row["price"] is None, float(row["price"] or 0), row["name"]))

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif rows:
        headers = ("Model", "Provider", "Public indicative price", "Default endpoint")
        values = [(row["name"], row["provider"], price_text(row), row["endpoint"]) for row in rows]
        widths = [max(len(header), *(len(value[index]) for value in values)) for index, header in enumerate(headers)]
        print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
        print("-+-".join("-" * width for width in widths))
        for value in values:
            print(" | ".join(cell.ljust(widths[index]) for index, cell in enumerate(value)))
        print("\nPrices are public indicative rates. Run estimate_video.py with the identical model and payload for the authoritative pre-submit price.")
    else:
        print("No matching available video models were returned.")

    if not args.no_save:
        snapshot = save_snapshot(rows)
        print(f"Catalog snapshot: {snapshot.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
