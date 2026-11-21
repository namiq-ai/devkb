#!/usr/bin/env python3
"""#369: why the benchmark's sessions refused commands, from the runs themselves.

Every refused call has the session's reason in its `tool_result` (is_error) in `stream.jsonl`; the run's `result`
event counts the refusals (`permission_denials`). This groups the refusals by that reason, per arm, and counts the
devkb calls the no-devkb arms refuse by design (#335) apart: no prompt wording removes those.

  python bench/policy/probes/denial_reasons.py RUN_DIR_OR_STREAM ...      # a table, then one JSON line per group
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

# the session's own wording, most specific first; for "contains multiple operations. The following part(s) require
# approval: ...", the parts it names
GROUPS = [
    ("devkb denied in a no-devkb arm", None),
    ("code with braces and quotes in the command", r"(?i)brace"),
    ("cd, then git", r"(?i)changes directory before running a version-control"),
    ("cd, then a redirect or a write", r"(?i)change directories and write|cannot automatically determine the final working directory"),
    ("sed -i", r"(?i)sed command requires approval|\bsed\s+-i"),
    ("a variable or an env-var prefix", r"(?i)variable|parameter expansion|(^|[;&|,:]\s*)[A-Z_][A-Z0-9_]*="),
    ("a path outside the checkout", r"(?i)allowed working director|outside the working director|was blocked|(^|[\s'\"=])\.\.(/|\s|$|;)|/tmp/|~/"),
    ("$(...), a subshell or a loop", r"(?i)command substitution|subshell|\bloop\b|\$\(|(^|[;&|]\s*)\(|\b(for|while)\s"),
    ("other", r"."),
]
NO_DEVKB = ("none", "nonehid", "nonekeep")


def refusals(stream: Path) -> tuple[str, list[tuple[str, str]]]:
    """(the run's arm, [(the refused command, the session's reason)])."""
    run = stream.parent.name
    arm = run.split("-")[1] if run.count("-") >= 2 else ""
    calls, reasons, denied = {}, {}, []
    for line in stream.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for b in e.get("message", {}).get("content", []) or []:
                if b.get("type") == "tool_use":
                    calls[b.get("id")] = b
        content = e.get("message", {}).get("content") if e.get("type") == "user" else None
        for b in content if isinstance(content, list) else []:
            if b.get("type") == "tool_result" and b.get("is_error"):
                c = b.get("content")
                reasons[b.get("tool_use_id")] = c if isinstance(c, str) else " ".join(
                    x.get("text", "") for x in c or [] if isinstance(x, dict))
        if e.get("type") == "result":
            denied = e.get("permission_denials", [])
    out = []
    for d in denied:
        cmd = (d.get("tool_input") or {}).get("command") or d.get("tool_name", "")
        out.append((cmd, reasons.get(d.get("tool_use_id"), "")))
    return arm, out


def group(arm: str, cmd: str, reason: str) -> str:
    parts = re.search(r"(?is)following parts? requires? approval:\s*(.*)", reason)
    text = parts.group(1) if parts else (reason or cmd)
    if arm in NO_DEVKB and re.search(r"(^|[;&|(]\s*)(\S*/)?(\.venv/bin/)?devkb\s", text if parts else cmd):
        return GROUPS[0][0]
    return next(name for name, pat in GROUPS[1:] if re.search(pat, text))


def main(paths: list[str]) -> int:
    streams = [s for p in map(Path, paths) for s in ([p] if p.is_file() else sorted(p.glob("*/stream.jsonl")))]
    runs, by_arm, groups, examples = collections.Counter(), collections.Counter(), collections.Counter(), {}
    for s in streams:
        arm, rs = refusals(s)
        runs[arm] += 1
        for cmd, reason in rs:
            g = group(arm, cmd, reason)
            groups[g] += 1
            by_arm[(arm, g)] += 1
            examples.setdefault(g, (cmd[:100].replace("\n", " "), reason[:140].replace("\n", " ")))
    total, n = sum(groups.values()), sum(runs.values())
    design = groups[GROUPS[0][0]]
    print(f"{n} runs, {total} refusals ({total / max(n, 1):.2f} per run); without the devkb denials of the no-devkb arms: "
          f"{total - design} ({(total - design) / max(n, 1):.2f} per run)")
    for g, c in groups.most_common():
        print(f"{c:4}  {g}")
    for g, c in groups.most_common():
        print(json.dumps({"group": g, "refusals": c, "by_arm": {a: v for (a, gg), v in by_arm.items() if gg == g},
                          "example": examples[g]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
