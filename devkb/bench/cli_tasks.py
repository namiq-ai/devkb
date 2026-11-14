#!/usr/bin/env python3
"""Benchmark tasks for a repository without HTTP route handlers (a command-line tool, a library).

  python3 devkb/bench/cli_tasks.py CHECKOUT OUT.json --seed 2029 --per-kind 8 --prefix L-

confirm_tasks.py asks which route handlers reach a function, which has no answer in a repository whose only entry
point is `main`. These two kinds keep its truth (import-path resolution, module_truth.py, never the graph) and ask
what a developer of such a repository asks before a change:

  rca       an error message (four or more words, raised once, a literal) in a module-level function: the raiser,
            every production function that reaches it through calls at any depth (2 to 15, a clean closure: every
            function on the way is a module-level function the truth sees), and every test file that calls the
            raiser or one of those functions
  refactor  a module-level function called from 4 to 25 files, tests among them but not all: the files with a
            direct caller, and the test files among them

Selection is shuffled with the seed; up to --per-kind tasks of each kind, one per function.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import module_truth as mt  # noqa: E402


def build(root: Path, seed: int, per_kind: int) -> list[dict]:
    T = mt.Truth(root)
    callers = T.callers()
    rnd = random.Random(seed)
    used: set[str] = set()
    tasks: list[dict] = []

    counts = collections.Counter(msg for f in T.files.values() for _q, msg in f.raises)
    errs = []
    for rel, f in T.files.items():
        if mt.is_test(rel):
            continue
        for qual, msg in f.raises:
            key = (rel, qual)
            if counts[msg] != 1 or len(msg.split()) < 4 or "{" in msg or not T.is_function(key):
                continue
            prod, tests, clean = T.up(key)
            test_files = sorted({k[0] for k in tests})
            if clean and 2 <= len(prod) <= 15 and test_files:
                errs.append((key, msg, sorted(mt.short(k) for k in prod), test_files))
    rnd.shuffle(errs)
    for key, msg, prod, test_files in errs:
        if len([t for t in tasks if t["kind"] == "rca"]) == per_kind:
            break
        if key[1] in used:
            continue
        used.add(key[1])
        tasks.append({"id": f"ERR-{key[1]}", "kind": "rca", "skill": "devkb-rca",
                      "prompt": (f'A user of this tool reports an error whose message is: "{msg}". Trace it: name the function that '
                                 "raises it, every function outside the tests that can reach that function through calls at any depth, "
                                 "and every test file that calls the raising function or any of those functions. Answer with one JSON "
                                 'object: {"raiser": "path::function", "callers": ["path::function", ...], "test_files": ["path", ...]}.'),
                      "truth": {"raiser": mt.short(key), "callers": prod, "test_files": test_files}})

    wide = []
    for rel, f in T.files.items():
        if mt.is_test(rel):
            continue
        for name in sorted(f.functions):
            key = (rel, name)
            if name in used or len(name) < 6:
                continue
            files = sorted({c[0] for c in callers.get(key, ())})
            if 4 <= len(files) <= 25 and 0 < sum(mt.is_test(x) for x in files) < len(files):
                wide.append((key, files))
    rnd.shuffle(wide)
    for key, files in wide[:per_kind]:
        used.add(key[1])
        tasks.append({"id": f"WIDE-{key[1]}", "kind": "refactor", "skill": "devkb-refactor",
                      "prompt": (f"You will change the signature of `{key[1]}` (defined in {key[0]}). Before editing, scope the change: "
                                 "list every file that contains a direct caller (tests included), and the test files among them. "
                                 'Answer with one JSON object: {"caller_files": [...], "test_files": [...]}.'),
                      "truth": {"caller_files": files, "test_files": [x for x in files if mt.is_test(x)]}})
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--per-kind", type=int, default=8)
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()
    tasks = build(Path(a.checkout), a.seed, a.per_kind)
    for t in tasks:
        t["id"] = a.prefix + t["id"]
        print(t["id"], {k: (len(v) if isinstance(v, list) else v) for k, v in t["truth"].items()})
    json.dump(tasks, open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
