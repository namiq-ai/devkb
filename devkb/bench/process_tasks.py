#!/usr/bin/env python3
"""Process-layer tasks for ADDENDUM-1 S2: joins across tickets, commits, code and tests, truth from git and source.

  python3 devkb/bench/process_tasks.py CHECKOUT PREFIX OUT.json --seed 2028 --per-kind 4 --tag A-

  ticket_code   for a ticket: the module-level functions its commits changed that still exist at HEAD, and the test
                files that call any of them. Commits: `git log HEAD --grep` on the ticket id, word-anchored. Changed
                functions: functions whose line range at that commit intersects a hunk of the commit's diff. Test
                callers: import-path resolution at HEAD (module_truth.py).
  commit_trace  (where tickets record `## Trace`) for a commit: its ticket, the ticket's epic and specification,
                read from the ticket file's Trace table.

Selection: tickets whose commits change 2 to 12 such functions, at least one with a test caller; shuffled with the
seed; up to --per-kind tasks of each kind. Nothing here reads the graph.
"""
from __future__ import annotations

import argparse
import ast
import json
import random
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import module_truth as mt  # noqa: E402

HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.M)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout


def commits_for(root: Path, ticket: str) -> list[str]:
    return git(root, "log", "HEAD", "--format=%H", "-E", f"--grep=(^|[^0-9A-Za-z-]){re.escape(ticket)}([^0-9]|$)").split()


def changed_functions(root: Path, commit: str) -> set[tuple[str, str]]:
    """Module-level functions whose body, at `commit`, intersects a hunk the commit added or changed."""
    out = set()
    files = [f for f in git(root, "show", "--format=", "--name-only", commit).split() if f.endswith(".py")]
    for rel in files:
        if mt.is_test(rel):
            continue
        diff = git(root, "show", "-U0", "--format=", commit, "--", rel)
        spans = []
        for m in HUNK.finditer(diff):
            start, n = int(m.group(1)), int(m.group(2) or 1)
            spans.append((start, start + max(n, 1) - 1))
        if not spans:
            continue
        try:
            tree = ast.parse(git(root, "show", f"{commit}:{rel}"))
        except (SyntaxError, ValueError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lo, hi = node.lineno, getattr(node, "end_lineno", node.lineno)
                if any(a <= hi and b >= lo for a, b in spans):
                    out.add((rel, node.name))
    return out


def trace(text: str) -> dict:
    rows = dict(re.findall(r"^\| (Epic|Specification) \| (\S+) \|", text, re.M))
    return {"epic": rows.get("Epic"), "spec": rows.get("Specification")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("prefix", help="the ticket prefix, e.g. OCO or ODSF")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--per-kind", type=int, default=4)
    ap.add_argument("--tag", default="")
    ap.add_argument("--exclude", help="JSON list of names and ticket ids used in exploratory tasks")
    a = ap.parse_args()
    root = Path(a.checkout)
    T = mt.Truth(root)
    callers = T.callers()
    head_functions = {(rel, n) for rel, f in T.files.items() for n in f.functions}
    files = sorted((root / "issues").glob(f"{a.prefix}-*.md"))
    rnd = random.Random(a.seed)
    rnd.shuffle(files)
    tasks, traced = [], []
    exclude = set(json.load(open(a.exclude))) if a.exclude else set()
    id_rx = re.compile(r"\b[A-Z]{2,6}-\d+\b")
    for path in files:
        ticket = re.match(rf"({re.escape(a.prefix)}-\d+)", path.name).group(1)
        if ticket in exclude:
            continue
        commits = commits_for(root, ticket)
        if not commits or len(commits) > 15:
            continue
        changed = set()
        for c in commits:
            changed |= changed_functions(root, c)
        changed &= head_functions
        if not 2 <= len(changed) <= 12:
            continue
        tests = sorted({c[0] for fn in changed for c in callers.get(fn, ()) if mt.is_test(c[0])})
        if tests and len([t for t in tasks if t["kind"] == "ticket_code"]) < a.per_kind:
            tasks.append({"id": f"{a.tag}TCODE-{ticket}", "kind": "ticket_code", "skill": "devkb-sdlc",
                          "prompt": (f"Ticket {ticket}: which module-level (top-level, not methods) Python functions did the commits that "
                                     "reference this ticket change, counting only functions that still exist in the current checkout, "
                                     "and which test files call any of those functions? Answer with one JSON object: "
                                     '{"functions": ["path::function", ...], "test_files": ["path", ...]}.'),
                          "truth": {"functions": sorted(mt.short(k) for k in changed), "test_files": tests,
                                    "commits": len(commits)}})
        tr = trace(path.read_text(errors="replace"))
        if tr["epic"] and tr["spec"]:
            # a commit naming one ticket only, so "which ticket does it reference" has one answer
            single = [c for c in commits if set(id_rx.findall(git(root, "log", "-1", "--format=%B", c))) == {ticket}]
            if single:
                traced.append((ticket, single[0], tr))
        if len([t for t in tasks if t["kind"] == "ticket_code"]) >= a.per_kind and len(traced) >= a.per_kind:
            break
    for ticket, commit, tr in traced[: a.per_kind]:
        tasks.append({"id": f"{a.tag}TRACE-{commit[:10]}", "kind": "commit_trace", "skill": "devkb-sdlc",
                      "prompt": (f"Commit {commit[:10]}: which ticket does it reference, which epic is that ticket's parent, and which "
                                 "specification does that ticket implement? Answer with one JSON object: "
                                 '{"ticket": "...", "epic": "...", "spec": "..."}.'),
                      "truth": {"ticket": ticket, "epic": tr["epic"], "spec": tr["spec"]}})
    json.dump(tasks, open(a.out, "w"), indent=1)
    for t in tasks:
        print(t["id"], {k: (len(v) if isinstance(v, list) else v) for k, v in t["truth"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
