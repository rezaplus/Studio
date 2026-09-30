#!/usr/bin/env python3
"""Agent client for Studio's sequential dubbing queue (HeyGen API mode).

Studio must be running (node studio/server.mjs). The queue runs items one at a time and
persists in runtime/queue/dubbing.json. Both steps are PAID and need separate confirmation:

  add      queue Proofread for items      (needs --yes-paid-proofread)
  render   final render for an item after its SRT review  (needs --yes-paid-render)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8789/api/queue/dubbing"


def call(method: str, url: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        sys.exit(f"Studio refused: {json.loads(error.read() or b'{}').get('error', error.reason)}")
    except urllib.error.URLError:
        sys.exit("Studio is not running. Start it with: node studio/server.mjs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("--item", action="append", required=True, metavar="PROJECT:RELEASE:LANG", help="e.g. cnt-20260929-x:tr-v1:ar (repeatable)")
    add.add_argument("--yes-paid-proofread", action="store_true")
    render = sub.add_parser("render")
    render.add_argument("id")
    render.add_argument("--yes-paid-render", action="store_true")
    cancel = sub.add_parser("cancel")
    cancel.add_argument("id")
    args = parser.parse_args()
    if args.cmd == "list":
        data = call("GET", BASE)
        print(f"HeyGen mode: {data['mode']}  balance: {data['balance']}")
        for i in data["items"]:
            print(f"{i['id']}  {i['state']:15} {i['projectId']} {i['releaseId']} -> {i['language']}" + (f"  ({i['error']})" if i.get("error") else ""))
    elif args.cmd == "add":
        items = []
        for value in args.item:
            project, release, language = value.split(":")
            items.append({"projectId": project, "releaseId": release, "language": language})
        print(json.dumps(call("POST", BASE, {"items": items, "paidConfirmation": args.yes_paid_proofread}), indent=2))
    elif args.cmd == "render":
        print(json.dumps(call("POST", f"{BASE}/{args.id}/render", {"paidConfirmation": args.yes_paid_render}), indent=2))
    else:
        print(json.dumps(call("POST", f"{BASE}/{args.id}/cancel", {}), indent=2))


if __name__ == "__main__":
    main()
