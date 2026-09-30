#!/usr/bin/env python3
"""Route a content request to its existing capability, pipeline, and script.

This command is read-only. It never calls a provider, creates content, or
submits a paid request. Agents must run it before choosing an implementation
path for a Studio request.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from provider_mode import PROVIDERS, mode  # noqa: E402
REGISTRY = ROOT / "config" / "capabilities.json"


def score(request: str, keywords: list[str]) -> int:
    return sum(len(keyword) for keyword in keywords if keyword.lower() in request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="User request in Persian, English, or Turkish")
    parser.add_argument("--json", action="store_true", help="Print JSON for an agent or Studio")
    args = parser.parse_args()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    query = args.request.strip().lower()
    ranked = sorted(
        ((score(query, item["keywords"]), item) for item in registry["capabilities"]),
        key=lambda pair: pair[0], reverse=True,
    )
    matched_score, matched = ranked[0]
    result = {
        "request": args.request,
        "matched": matched_score > 0,
        "resolutionOrder": registry["resolutionOrder"],
        "capability": matched if matched_score > 0 else None,
        "providerModes": {name: mode(name) for name in PROVIDERS},
        "nextAction": (
            f"Run {matched['entryScript']} through pipeline {matched['pipeline']}."
            if matched_score > 0
            else "No capability matched. Read the relevant profile and propose a new pipeline only after checking existing scripts."
        ),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["matched"]:
        print(f"Capability: {matched['id']}")
        print(f"Pipeline: {matched['pipeline']}")
        print(f"Entry script: {matched['entryScript']}")
        print("Required input: " + ", ".join(matched["requiredInputs"]))
        print("Paid gate: " + ("required" if matched["paid"] else "not required"))
        print("Resolution order: " + " → ".join(registry["resolutionOrder"]))
        print("Provider modes: " + " ".join(f"{n}={mode(n)}" for n in PROVIDERS) + "  (api = scripts + .env keys; mcp = agent MCP tools only)")
    else:
        print(result["nextAction"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
