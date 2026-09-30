#!/usr/bin/env python3
"""Workspace defaults: config/workspace.json overlaid by the git-ignored config/workspace.local.json.

Keep shareable defaults in workspace.json. Put personal choices (your brand, locales, provider
language targets) in workspace.local.json so the repository stays generic.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def load() -> dict:
    data = json.loads((CONFIG / "workspace.json").read_text(encoding="utf-8"))
    local = CONFIG / "workspace.local.json"
    if local.is_file():
        data = _merge(data, json.loads(local.read_text(encoding="utf-8")))
    return data


def default_brand() -> str:
    return load()["defaultBrand"]


def default_locales() -> str:
    return ",".join(load().get("activeLocales") or ["en"])


def brand(name: str | None = None) -> dict:
    name = name or default_brand()
    path = CONFIG / "brands" / name / "brand.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def subtitle_preset(brand_name: str | None = None) -> str:
    return brand(brand_name).get("subtitlePreset") or "creator"


if __name__ == "__main__":
    print(json.dumps(load(), ensure_ascii=False, indent=2))
