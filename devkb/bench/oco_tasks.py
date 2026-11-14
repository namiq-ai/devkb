#!/usr/bin/env python3
"""Multi-hop workflow tasks on a large repository (ODSF-310, run on OCO): ground truth from source, never from devkb.

The ODSF workflow benchmark (docs/workflow-benchmark-odsf310.md) asked one-hop questions that `git grep` answers in a
few turns. These ask what a developer needs before a change in a large codebase, where the answer is a closure:

  err_to_handler  an error message raised once, in non-route code: the raiser, every HTTP route handler that can
                  reach it through calls at any depth, and the test files that call any function on those paths
  impact          a function reachable from three or more route handlers: those handlers, and the tests to run
  wide_refactor   a function called from 8 to 25 files: the caller files, the test files, and the files the role
                  may not edit

Calls are resolved by workflow_tasks.callers_of (through imports; a name a library type shares is never matched by
name alone). A task is kept only when every function on its paths has a name defined once in the repository, so no
step in the closure depends on a guess.

  python3 devkb/bench/oco_tasks.py CHECKOUT OUT.json
"""
from __future__ import annotations

import ast
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow_tasks as wt  # noqa: E402

ROUTE_VERBS = {"get", "post", "put", "delete", "patch"}
MAX_DEPTH = 6


def handlers(root: Path, s: dict) -> set[tuple[str, str]]:
    """Functions decorated `@<something>.get(...)` and the like: FastAPI route handlers."""
    out = set()
    for rel in {k[0] for k in s["calls"]}:
        try:
            tree = ast.parse((root / rel).read_text(errors="replace"))
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_VERBS:
                        out.add((rel, node.name))
    return out


def up_closure(s: dict, unique: dict, start: str) -> tuple[set, set, bool]:
    """Every function that reaches `start` through calls, and whether the walk stayed unambiguous."""
    seen: set = set()
    frontier, clean = [start], True
    for _ in range(MAX_DEPTH):
        nxt = []
        for name in frontier:
            for caller in wt.callers_of(s, name):
                if caller in seen:
                    continue
                seen.add(caller)
                if wt.is_test_file(caller[0]):
                    continue  # a test ends a path; it is not a route to anything
                cname = caller[1].split(".")[-1]
                if unique.get(cname) != caller:
                    clean = False  # its own callers cannot be found by name without guessing
                    continue
                nxt.append(cname)
        frontier = nxt
        if not frontier:
            break
    else:
        clean = clean and not frontier
    tests = {k for k in seen if wt.is_test_file(k[0])}
    return seen - tests, tests, clean


def build(root: Path, seed: int = 311, per_kind: int = 2, exclude: set[str] | None = None,
          impact_prefixes: tuple[str, ...] | None = ("webapp/backend/app/services", "webapp/backend/app/", "scripts/"),
          ) -> list[dict]:
    """The exploratory set used the defaults. The confirmatory study (ODSF-315, PREREGISTRATION.md) passes a new seed,
    four tasks per kind, the exploratory names as `exclude`, and `impact_prefixes=None` (any non-test file)."""
    exclude = set(exclude or ())
    s = wt.scan(root)
    unique = {n: ks[0] for n, ks in s["defs"].items() if len(ks) == 1 and not n.startswith("test_") and not n.startswith("__")}
    routes = handlers(root, s)
    route_names = {(r, q.split(".")[-1]) for r, q in routes}
    rnd = random.Random(seed)
    tasks: list[dict] = []

    def reach(name):
        prod, tests, clean = up_closure(s, unique, name)
        hit = sorted(wt.short(k) for k in prod if (k[0], k[1].split(".")[-1]) in route_names)
        test_files = sorted({k[0] for k in tests} | {c[0] for c in wt.callers_of(s, name) if wt.is_test_file(c[0])})
        return prod, hit, test_files, clean

    used: set[str] = set(exclude)
    counts = collections.Counter(msg for _, msg in s["raises"])
    errs = []
    for key, msg in s["raises"]:
        name = key[1].split(".")[-1]
        if name in used or counts[msg] != 1 or len(msg.split()) < 4 or "{" in msg or unique.get(name) != key or wt.is_test_file(key[0]):
            continue
        if (key[0], name) in route_names:
            continue  # raised in the handler itself is one hop, not a trace
        prod, hit, tests, clean = reach(name)
        if clean and 1 <= len(hit) <= 12 and tests and len(prod) >= 2:
            errs.append((key, msg, hit, tests, len(prod)))
    # every clean chain in OCO reaches one handler; the deepest chains are the hardest traces
    errs.sort(key=lambda e: (-e[4], -len(e[3]), e[0]))
    for key, msg, hit, tests, n in errs[:per_kind]:
        name = key[1].split(".")[-1]
        used.add(name)
        tasks.append({"id": f"ERR-{name}", "stage": "RCA", "kind": "err_to_handler", "skill": "devkb-rca",
                      "prompt": (f'Users of the web API get an error whose message is: "{msg}". Trace it: name the function that raises it, '
                                 "every HTTP route handler function (a function decorated as a FastAPI route) that can reach that function "
                                 "through calls at any depth, and every test file that calls the raising function or any function on a path "
                                 "between it and those handlers. Answer with one JSON object: "
                                 '{"raiser": "path::function", "handlers": ["path::function", ...], "test_files": ["path", ...]}.'),
                      "truth": {"raiser": wt.short(key), "handlers": hit, "test_files": tests, "closure_size": n}})

    imp = []
    for name, key in unique.items():
        if name in used or wt.is_test_file(key[0]) or (key[0], name) in route_names or len(name) < 8:
            continue
        if impact_prefixes and not key[0].startswith(impact_prefixes):
            continue
        prod, hit, tests, clean = reach(name)
        if clean and 3 <= len(hit) <= 15 and tests and len(prod) >= 4:
            imp.append((name, key, hit, tests, len(prod)))
    rnd.shuffle(imp)
    for name, key, hit, tests, n in imp[:per_kind]:
        used.add(name)
        tasks.append({"id": f"IMP-{name}", "stage": "IMPACT", "kind": "impact", "skill": "devkb-feature",
                      "prompt": (f"You are about to change the behaviour of `{name}` (defined in {key[0]}). Before editing, find which HTTP route "
                                 "handler functions (functions decorated as FastAPI routes) can reach it through calls at any depth, and which "
                                 "test files you must run: every test file that calls it or any function on a path between it and those handlers. "
                                 'Answer with one JSON object: {"handlers": ["path::function", ...], "test_files": ["path", ...]}.'),
                      "truth": {"handlers": hit, "test_files": tests, "closure_size": n}})

    roles = wt.dnt(root)
    wide = []
    for name, key in unique.items():
        if name in used or wt.is_test_file(key[0]) or len(name) < 8:
            continue
        files = sorted({c[0] for c in wt.callers_of(s, name)})
        if not (8 <= len(files) <= 25 and any(wt.is_test_file(f) for f in files)):
            continue
        for role, prefixes in sorted(roles.items()):
            blocked = sorted(f for f in files if any(f.startswith(p) for p in prefixes))
            if 1 <= len(blocked) < len(files) and not any(key[0].startswith(p) for p in prefixes):
                wide.append((name, key, files, role, blocked))
                break
    if len(wide) < per_kind and roles:
        # In OCO no role is barred from part of a wide function's callers without also being barred from the function
        # itself, so the widest functions are scoped by a role that may edit them: the right boundary answer is [].
        extra = []
        for name, key in unique.items():
            if name in used or name in {w[0] for w in wide} or wt.is_test_file(key[0]) or len(name) < 8:
                continue
            files = sorted({c[0] for c in wt.callers_of(s, name)})
            if 12 <= len(files) <= 25 and 0 < sum(wt.is_test_file(f) for f in files) < len(files):
                role = next((r for r, p in sorted(roles.items(), key=lambda rp: -len(rp[1]))
                             if p and not any(key[0].startswith(x) for x in p)), "TL")
                extra.append((len(files), name, key, files, role,
                              sorted(f for f in files if any(f.startswith(x) for x in roles.get(role, [])))))
        extra.sort(key=lambda e: -e[0])
        wide += [e[1:] for e in extra[: per_kind - len(wide)]]
    if not roles:
        # A repository with no role profiles (a public project): the same refactor, without the boundary question.
        cand = []
        for name, key in unique.items():
            if name in used or wt.is_test_file(key[0]) or len(name) < 8:
                continue
            files = sorted({c[0] for c in wt.callers_of(s, name)})
            if 8 <= len(files) <= 25 and 0 < sum(wt.is_test_file(f) for f in files) < len(files):
                cand.append((name, key, files))
        rnd.shuffle(cand)
        for name, key, files in cand[:per_kind]:
            tasks.append({"id": f"WIDE-{name}", "stage": "REFACTOR", "kind": "refactor", "skill": "devkb-refactor",
                          "prompt": (f"You will change the signature of `{name}` (defined in {key[0]}). Before editing, scope the change: "
                                     "list every file that contains a direct caller (tests included), and the test files among them. "
                                     'Answer with one JSON object: {"caller_files": [...], "test_files": [...]}.'),
                          "truth": {"caller_files": files, "test_files": [f for f in files if wt.is_test_file(f)]}})
        return tasks
    rnd.shuffle(wide)
    for name, key, files, role, blocked in wide[:per_kind]:
        tasks.append({"id": f"WIDE-{name}", "stage": "REFACTOR", "kind": "refactor", "skill": "devkb-refactor",
                      "prompt": (f"You work as role {role} and will change the signature of `{name}` (defined in {key[0]}). Before editing, scope the "
                                 "change: list every file that contains a direct caller (tests included), the test files among them, and which of "
                                 f"those files role {role} must not edit according to the DO NOT TOUCH block of its profile in sdp/process/roles. "
                                 'Answer with one JSON object: {"caller_files": [...], "test_files": [...], "blocked_files": [...]}.'),
                      "truth": {"caller_files": files, "test_files": [f for f in files if wt.is_test_file(f)], "blocked_files": blocked}})
    return tasks


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=311)
    ap.add_argument("--per-kind", type=int, default=2)
    ap.add_argument("--exclude", help="a JSON list of function names already used")
    ap.add_argument("--any-path", action="store_true", help="draw impact tasks from any non-test file")
    ap.add_argument("--prefix", default="", help="prefix task ids, e.g. the repository id")
    a = ap.parse_args()
    t = build(Path(a.checkout), seed=a.seed, per_kind=a.per_kind,
              exclude=set(json.load(open(a.exclude))) if a.exclude else None,
              impact_prefixes=None if a.any_path else ("webapp/backend/app/services", "webapp/backend/app/", "scripts/"))
    for x in t:
        x["id"] = a.prefix + x["id"]
    sys.argv = [sys.argv[0], a.checkout, a.out]
    json.dump(t, open(sys.argv[2], "w"), indent=1)
    for x in t:
        print(x["id"], {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in x["truth"].items()})
