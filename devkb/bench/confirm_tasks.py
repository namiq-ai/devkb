#!/usr/bin/env python3
"""Confirmatory task set (ODSF-315, PREREGISTRATION.md): the three exploratory task kinds on import-path truth.

  python3 devkb/bench/confirm_tasks.py CHECKOUT OUT.json --seed 2027 --per-kind 4 --exclude names.json --prefix C-

Selection, fixed before any confirmatory run:
  err_to_handler  a literal message of four or more words raised once, in a module-level non-route function; clean
                  closure; one to twelve route handlers reach it; at least one test file on the paths; deepest first;
                  one task per raising function
  impact          a module-level non-test, non-route function; clean closure; three to fifteen handlers; a test file;
                  four or more production callers; shuffled with the seed
  refactor        a module-level function called from eight to twenty-five files, tests among them but not all;
                  shuffled with the seed; the role-boundary question only where the repository declares roles
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
import workflow_tasks as wt  # noqa: E402


def build(root: Path, seed: int, per_kind: int, exclude: set[str]) -> list[dict]:
    T = mt.Truth(root)
    callers = T.callers()
    rnd = random.Random(seed)
    used = set(exclude)
    tasks: list[dict] = []

    def reach(key):
        prod, tests, clean = T.up(key)
        handlers = sorted(mt.short(k) for k in prod if T.is_route(k))
        test_files = sorted({k[0] for k in tests})
        return prod, handlers, test_files, clean

    counts = collections.Counter(msg for f in T.files.values() for _q, msg in f.raises)
    errs = []
    for rel, f in T.files.items():
        if mt.is_test(rel):
            continue
        for qual, msg in f.raises:
            key = (rel, qual)
            if (qual in used or counts[msg] != 1 or len(msg.split()) < 4 or "{" in msg or not T.is_function(key)
                    or T.is_route(key)):
                continue
            prod, hs, tests, clean = reach(key)
            if clean and 1 <= len(hs) <= 12 and tests and len(prod) >= 1:
                errs.append((key, msg, hs, tests, len(prod)))
    errs.sort(key=lambda e: (-e[4], -len(e[3]), e[0]))
    chosen = 0
    for key, msg, hs, tests, n in errs:
        if chosen == per_kind:
            break
        if key[1] in used:
            continue  # one task per raising function, even when it raises several messages
        chosen += 1
        used.add(key[1])
        tasks.append({"id": f"ERR-{key[1]}", "kind": "err_to_handler", "skill": "devkb-rca",
                      "prompt": (f'Users of the web API get an error whose message is: "{msg}". Trace it: name the function that raises it, '
                                 "every HTTP route handler function (a function decorated as a FastAPI route) that can reach that function "
                                 "through calls at any depth, and every test file that calls the raising function or any function on a path "
                                 "between it and those handlers. Answer with one JSON object: "
                                 '{"raiser": "path::function", "handlers": ["path::function", ...], "test_files": ["path", ...]}.'),
                      "truth": {"raiser": mt.short(key), "handlers": hs, "test_files": tests, "closure_size": n}})

    imp = []
    for rel, f in T.files.items():
        if mt.is_test(rel):
            continue
        for name in sorted(f.functions):
            key = (rel, name)
            if name in used or len(name) < 8 or T.is_route(key):
                continue
            prod, hs, tests, clean = reach(key)
            if clean and 3 <= len(hs) <= 15 and tests and len(prod) >= 4:
                imp.append((key, hs, tests, len(prod)))
    rnd.shuffle(imp)
    for key, hs, tests, n in imp[:per_kind]:
        used.add(key[1])
        tasks.append({"id": f"IMP-{key[1]}", "kind": "impact", "skill": "devkb-feature",
                      "prompt": (f"You are about to change the behaviour of `{key[1]}` (defined in {key[0]}). Before editing, find which HTTP route "
                                 "handler functions (functions decorated as FastAPI routes) can reach it through calls at any depth, and which "
                                 "test files you must run: every test file that calls it or any function on a path between it and those handlers. "
                                 'Answer with one JSON object: {"handlers": ["path::function", ...], "test_files": ["path", ...]}.'),
                      "truth": {"handlers": hs, "test_files": tests, "closure_size": n}})

    roles = wt.dnt(root)
    wide = []
    for rel, f in T.files.items():
        if mt.is_test(rel):
            continue
        for name in sorted(f.functions):
            key = (rel, name)
            if name in used or len(name) < 8:
                continue
            files = sorted({c[0] for c in callers.get(key, ())})
            if not (8 <= len(files) <= 25 and 0 < sum(mt.is_test(x) for x in files) < len(files)):
                continue
            role, blocked = "", None
            for r, prefixes in sorted(roles.items()):
                b = sorted(x for x in files if any(x.startswith(p) for p in prefixes))
                if b and len(b) < len(files) and not any(rel.startswith(p) for p in prefixes):
                    role, blocked = r, b
                    break
            wide.append((key, files, role, blocked))
    rnd.shuffle(wide)
    for key, files, role, blocked in wide[:per_kind]:
        tests = [x for x in files if mt.is_test(x)]
        if role:
            prompt = (f"You work as role {role} and will change the signature of `{key[1]}` (defined in {key[0]}). Before editing, scope "
                      "the change: list every file that contains a direct caller (tests included), the test files among them, and which "
                      f"of those files role {role} must not edit according to the DO NOT TOUCH block of its profile in sdp/process/roles. "
                      'Answer with one JSON object: {"caller_files": [...], "test_files": [...], "blocked_files": [...]}.')
            truth = {"caller_files": files, "test_files": tests, "blocked_files": blocked}
        else:
            prompt = (f"You will change the signature of `{key[1]}` (defined in {key[0]}). Before editing, scope the change: "
                      "list every file that contains a direct caller (tests included), and the test files among them. "
                      'Answer with one JSON object: {"caller_files": [...], "test_files": [...]}.')
            truth = {"caller_files": files, "test_files": tests}
        tasks.append({"id": f"WIDE-{key[1]}", "kind": "refactor", "skill": "devkb-refactor", "prompt": prompt, "truth": truth})
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--per-kind", type=int, default=4)
    ap.add_argument("--exclude")
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()
    tasks = build(Path(a.checkout), a.seed, a.per_kind, set(json.load(open(a.exclude))) if a.exclude else set())
    for t in tasks:
        t["id"] = a.prefix + t["id"]
    json.dump(tasks, open(a.out, "w"), indent=1)
    for t in tasks:
        print(t["id"], {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in t["truth"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
