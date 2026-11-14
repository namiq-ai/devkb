#!/usr/bin/env python3
"""How much of the call graph devkb actually holds (ODSF-305).

Picks a fixed random sample of functions that are defined exactly once in the
repository and have 3 to 10 callers and at least 2 tests, finds their true
callers with an AST scan that shares no code with devkb, then asks the graph
the same question. Reports caller recall and precision and test-file recall.

On 2026-11-13 the graph returned 4 of 36 true callers (11 percent) and none of
the tests for such a sample, which is why this exists: a graph that answers
"who calls this?" from a tenth of the answer is worse than no graph.

Usage:
  python3 devkb/call_recall.py --project ODSF            # report
  python3 devkb/call_recall.py --project ODSF --check    # exit 1 below a floor
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import random
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.project_context import resolve  # noqa: E402

SAMPLE_SIZE = 6
SEED = 7
FLOORS = {"caller_recall": 0.8, "caller_precision": 0.9, "test_file_recall": 0.8}
_SKIP = re.compile(r"(^|/)(\.impl-worktrees|node_modules|\.claude)/")


class _Scan(ast.NodeVisitor):
    def __init__(self, rel: str, defs: collections.Counter, calls: dict) -> None:
        self.rel, self.defs, self.calls = rel, defs, calls
        self.stack: list[str] = []
        self.fn: list[tuple[str, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.defs[node.name] += 1
        key = (self.rel, ".".join(self.stack + [node.name]))
        self.calls.setdefault(key, set())
        self.fn.append(key)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()
        self.fn.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_Call(self, node: ast.Call) -> None:
        if self.fn:
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name:
                self.calls[self.fn[-1]].add(name)
        self.generic_visit(node)


def truth(repo_root: Path) -> list[dict]:
    files = [f for f in subprocess.run(["git", "ls-files", "--recurse-submodules", "*.py"], cwd=repo_root, capture_output=True,
                                       text=True, check=False).stdout.split() if not _SKIP.search(f)]
    defs: collections.Counter = collections.Counter()
    calls: dict[tuple[str, str], set[str]] = {}
    for rel in files:
        try:
            _Scan(rel, defs, calls).visit(ast.parse((repo_root / rel).read_text(errors="replace")))
        except (SyntaxError, ValueError, OSError, RecursionError):
            continue
    is_test = lambda k: k[1].split(".")[-1].startswith("test_")  # noqa: E731
    pool = []
    for name, count in sorted(defs.items()):
        if count != 1 or len(name) < 9 or name.startswith("__") or name.startswith("test_"):
            continue
        callers = sorted(k for k, s in calls.items() if name in s)
        tests = [k for k in callers if is_test(k)]
        if 3 <= len(callers) <= 10 and 2 <= len(tests) <= 10 and any(not is_test(k) for k in callers):
            pool.append((name, callers))
    random.Random(SEED).shuffle(pool)
    short = lambda k: f"{k[0]}::{k[1].split('.')[-1]}"  # noqa: E731
    return [{"function": n, "callers": sorted({short(k) for k in cs}),
             "test_files": sorted({k[0] for k in cs if is_test(k)})} for n, cs in sorted(pool[:SAMPLE_SIZE])]


def graph_answers(devkb_dir: Path, function: str) -> tuple[set[str], set[str]] | None:
    nodes = {}
    by_short: dict[str, list[str]] = collections.defaultdict(list)
    for line in (devkb_dir / "nodes.jsonl").read_text().splitlines():
        n = json.loads(line)
        nodes[n["uid"]] = n
        if n["type"] == "Symbol":
            by_short[n["natural_key"].split("::", 1)[-1].split(".")[-1]].append(n["uid"])
    if len(by_short.get(function, [])) != 1:
        return None
    uid = by_short[function][0]
    callers: set[str] = set()
    tests: set[str] = set()
    for line in (devkb_dir / "edges.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["verb"] == "CALLS" and e["to_uid"] == uid:
            key = nodes[e["from_uid"]]["natural_key"]
            callers.add(f"{key.split('::')[0]}::{key.split('::')[-1].split('.')[-1]}")
        elif e["verb"] == "TESTED_BY" and e["from_uid"] == uid:
            tests.add(nodes[e["to_uid"]]["natural_key"].split(":")[0])
    return callers, tests


def measure(code: str) -> dict:
    ctx = resolve(code)
    rows = []
    for q in truth(ctx.repo_root):
        got = graph_answers(ctx.devkb_dir, q["function"])
        callers, tests = got if got else (set(), set())
        want_c, want_t = set(q["callers"]), set(q["test_files"])
        rows.append({"function": q["function"], "true_callers": len(want_c), "graph_callers": len(callers),
                     "caller_hits": len(callers & want_c), "true_test_files": len(want_t),
                     "test_file_hits": len(tests & want_t)})
    tc, hits = sum(r["true_callers"] for r in rows), sum(r["caller_hits"] for r in rows)
    gc = sum(r["graph_callers"] for r in rows)
    tt, th = sum(r["true_test_files"] for r in rows), sum(r["test_file_hits"] for r in rows)
    result = {"caller_recall": hits / tc if tc else 1.0, "caller_precision": hits / gc if gc else 0.0,
              "test_file_recall": th / tt if tt else 1.0}
    return {"project": code, "rows": rows, "totals": result,
            "ok": all(result[k] >= v for k, v in FLOORS.items())}


def main() -> int:
    ap = argparse.ArgumentParser(description="devkb call-graph recall against an independent AST scan")
    ap.add_argument("--project", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = measure(args.project)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"devkb call recall ({args.project}), {len(out['rows'])} sampled functions")
        for r in out["rows"]:
            print(f"  {r['function']:<32} callers {r['caller_hits']}/{r['true_callers']} (graph returned {r['graph_callers']})"
                  f"  test files {r['test_file_hits']}/{r['true_test_files']}")
        for k, v in out["totals"].items():
            print(f"  {k:<18} {v:.2f}  floor {FLOORS[k]:.2f}  {'ok' if v >= FLOORS[k] else 'FAIL'}")
    return 1 if args.check and not out["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
