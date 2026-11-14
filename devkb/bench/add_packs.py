#!/usr/bin/env python3
"""Attach a predefined graph pack to each workflow benchmark task (ODSF-313).

The pack is built from what the task's prompt states and nothing else (the error message; the function and the file
it is defined in; the role), the same input a build loop has from a ticket. The truth is never read here.

  DEVKB_DIR=<snapshot> DEVKB_REPO=<checkout> python3 devkb/bench/add_packs.py OCO TASKS.json OUT.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from devkb.packs import Packer  # noqa: E402
from devkb.process_api import ProcessAPI  # noqa: E402


def inputs(task: dict) -> tuple[str, dict]:
    prompt = task["prompt"]
    if task["kind"] == "ticket_code":  # ADDENDUM-1 S2
        return "ticket", {"ticket_id": re.search(r"Ticket ([A-Z]+-\d+)", prompt).group(1)}
    if task["kind"] == "commit_trace":
        return "commit_trace", {"commit": re.search(r"Commit ([0-9a-f]{7,40})", prompt).group(1)}
    if task["kind"] == "err_to_handler":
        return "error", {"message": re.search(r'"(.+?)"\. ', prompt).group(1)}
    name = re.search(r"`([^`]+)`", prompt).group(1)
    path = re.search(r"\(defined in ([^)]+)\)", prompt).group(1)
    if task["kind"] == "impact":
        return "change", {"name": name, "path": path}
    m = re.search(r"as role (\w+)", prompt)
    return "refactor", {"name": name, "role": m.group(1) if m else "", "path": path}


def main() -> int:
    code, src, dst = sys.argv[1:4]
    packer = Packer(ProcessAPI(code, telemetry=False))
    tasks = json.load(open(src))
    for t in tasks:
        kind, kw = inputs(t)
        t["pack"] = getattr(packer, kind)(**kw)
        t["pack_inputs"] = {"kind": kind, **kw}
        print(t["id"], kind, len(t["pack"].split()), "words")
    json.dump(tasks, open(dst, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
