#!/usr/bin/env python3
"""Per-provider transport choice: `api` (scripts + API keys) or `mcp` (agent MCP tools).

The mode lives in .env as HIGGSFIELD_MODE / HEYGEN_MODE (set in Studio Settings).
Unset means `api`. API scripts call require_api() so a provider set to MCP is
never reached through the API by accident.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = {"higgsfield": "HIGGSFIELD_MODE", "heygen": "HEYGEN_MODE"}


def _dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip("'\"")
    except OSError:
        pass
    return values


def mode(provider: str) -> str:
    key = PROVIDERS[provider]
    value = (_dotenv().get(key) or os.environ.get(key) or "api").strip().lower()
    return value if value in ("api", "mcp") else "api"


def require_api(provider: str) -> None:
    if mode(provider) == "mcp":
        sys.stderr.write(
            f"{provider} is set to MCP ({PROVIDERS[provider]}=mcp). This API script is disabled. "
            f"Use the {provider} MCP tools from the agent chat, or switch {provider} to API in Studio Settings.\n"
        )
        raise SystemExit(3)


if __name__ == "__main__":
    print(" ".join(f"{name}={mode(name)}" for name in PROVIDERS))
