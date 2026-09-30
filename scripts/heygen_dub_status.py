#!/usr/bin/env python3
"""Read a HeyGen V3 translation status without creating another job."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).with_name("heygen_dub.py")
SPEC = importlib.util.spec_from_file_location("heygen_dub", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load heygen_dub.py")
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("translation_id")
    args = parser.parse_args()
    CLIENT.load_dotenv(CLIENT.ROOT / ".env")
    data = CLIENT.request_json(f"/video-translations/{args.translation_id}")
    path = CLIENT.save_json("status", f"{CLIENT.timestamp()}-{args.translation_id}.json", data)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Saved: {path.relative_to(CLIENT.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
