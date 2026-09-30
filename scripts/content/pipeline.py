#!/usr/bin/env python3
"""Inspect and advance declarative Content Generator pipelines without provider calls."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = ROOT / "content"
PIPELINES_ROOT = ROOT / "config" / "pipelines"
TERMINAL = {"completed", "skipped"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def content_path(value: str) -> Path:
    path = (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if path.parent != CONTENT_ROOT or not path.is_dir():
        raise ValueError("Content must be a direct child of content/.")
    return path


def pipeline(name: str) -> dict:
    path = PIPELINES_ROOT / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"Unknown pipeline: {name}")
    return read_json(path)


def load_state(content: Path) -> dict:
    path = content / "pipeline.json"
    if path.is_file():
        return read_json(path)
    record = read_json(content / "content.json")
    return {"schemaVersion": 1, "contentId": record["id"], "pipeline": "reel-main", "stages": {}}


def save_state(content: Path, state: dict) -> None:
    state["updatedAt"] = datetime.now(timezone.utc).isoformat()
    (content / "pipeline.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init_cmd = sub.add_parser("init", help="Create pipeline state without running any stage.")
    init_cmd.add_argument("content")
    plan_cmd = sub.add_parser("plan", help="Show main pipeline progress and next stage.")
    plan_cmd.add_argument("content")
    plan_cmd.add_argument("--pipeline", help="Inspect one child pipeline without executing it.")
    set_cmd = sub.add_parser("set-stage", help="Record a non-provider stage result.")
    set_cmd.add_argument("content")
    set_cmd.add_argument("stage")
    set_cmd.add_argument("status", choices=("completed", "blocked", "skipped"))
    args = parser.parse_args()
    content = content_path(args.content)
    state = load_state(content)
    definition = pipeline(getattr(args, "pipeline", None) or state.get("pipeline", "reel-main"))
    stages = {stage["id"]: stage for stage in definition["stages"]}
    if args.command == "init":
        state["contentId"] = read_json(content / "content.json")["id"]
        state.setdefault("pipeline", "reel-main")
        state.setdefault("stages", {})
        save_state(content, state)
        print(f"INITIALIZED: {content.relative_to(ROOT)}")
        return 0
    if args.command == "set-stage":
        if args.stage not in stages:
            parser.error(f"Unknown stage for {definition['id']}: {args.stage}")
        state.setdefault("stages", {})[args.stage] = {"status": args.status, "updatedAt": datetime.now(timezone.utc).isoformat()}
        save_state(content, state)
    next_stage = None
    for stage in definition["stages"]:
        result = state.get("stages", {}).get(stage["id"], {})
        status = result.get("status", "pending")
        if status not in TERMINAL and next_stage is None:
            next_stage = stage
        print(f"{stage['id']}: {status}")
    if next_stage:
        print(f"NEXT: {next_stage['id']} ({next_stage['type']})")
        if next_stage.get("pipeline"):
            print(f"CHILD PIPELINE: {next_stage['pipeline']}")
    else:
        print("PIPELINE COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
