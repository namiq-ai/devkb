#!/usr/bin/env python3
"""Workflow benchmark tasks (ODSF-310): whole developer tasks with ground truth from source, never from devkb.

Truth is a plain AST scan of the pinned checkout: a call is counted by the called name, and only names defined
exactly once in the repository are used, so a name-based call is unambiguous. Role boundaries come from the role
profiles' DO NOT TOUCH blocks, read the way sdp/orchestrator/boundary_check.py reads them.

  python3 devkb/bench/workflow_tasks.py CHECKOUT OUT.json
"""
from __future__ import annotations

import ast
import collections
import json
import random
import re
import subprocess
import sys
import pathlib
from pathlib import Path

SKIP = re.compile(r"(^|/)(\.impl-worktrees|node_modules|\.claude|_bmad)/")


def is_test_file(p: str) -> bool:
    return bool(re.search(r"(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$", p))


class Scan(ast.NodeVisitor):
    """Functions, the names each one calls, and the literal messages each one raises."""

    def __init__(self, rel: str, out: dict) -> None:
        self.rel, self.out, self.stack, self.fn = rel, out, [], []

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _function(self, node):
        key = (self.rel, ".".join(self.stack + [node.name]))
        self.out["defs"][node.name].append(key)
        self.out["calls"].setdefault(key, set())
        self.out["complexity"][key] = 1 + sum(isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp, ast.IfExp))
                                              for n in ast.walk(node))
        self.stack.append(node.name)
        self.fn.append(key)
        self.generic_visit(node)
        self.fn.pop()
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def visit_Import(self, node):
        for a in node.names:
            self.out["mod_alias"][self.rel][a.asname or a.name.split(".")[0]] = a.name.split(".")[-1] if a.asname else a.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        mod = (node.module or "").split(".")[-1]
        for a in node.names:
            # `from devkb import project_context` binds a module; `from devkb.project_context import resolve` a function
            self.out["from_imp"][self.rel][a.asname or a.name] = (mod, a.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        if self.fn:
            f = node.func
            if isinstance(f, ast.Name):
                self.out["calls"][self.fn[-1]].add(("name", "", f.id))
            elif isinstance(f, ast.Attribute):
                base = f.value.id if isinstance(f.value, ast.Name) else ""
                self.out["calls"][self.fn[-1]].add(("attr", base, f.attr))
        self.generic_visit(node)

    def visit_Raise(self, node):
        if self.fn and isinstance(node.exc, ast.Call) and node.exc.args:
            a = node.exc.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                self.out["raises"].append((self.fn[-1], a.value))
        self.generic_visit(node)


def scan(root: Path) -> dict:
    out = {"defs": collections.defaultdict(list), "calls": {}, "raises": [], "complexity": {},
           "mod_alias": collections.defaultdict(dict), "from_imp": collections.defaultdict(dict)}
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=root, capture_output=True, text=True).stdout.split()
    for rel in files:
        if SKIP.search(rel):
            continue
        try:
            Scan(rel, out).visit(ast.parse((root / rel).read_text(errors="replace")))
        except (SyntaxError, ValueError, OSError, RecursionError):
            continue
    return out


# Method names that library objects also have (`Path.resolve`, `dict.get`, `str.split`...): a call `x.resolve()` on an
# unknown object is not evidence of a call to this repository's `resolve`.
COLLIDE = set().union(*(dir(t) for t in (str, bytes, list, dict, set, tuple, int, float, object, pathlib.Path)),
                      {"run", "get", "read", "write", "close", "update", "add", "send", "start", "stop", "load", "dump",
                       "dumps", "loads", "open", "search", "match", "group", "communicate", "wait", "kill", "main"})


def callers_of(s: dict, name: str) -> list[tuple[str, str]]:
    """Direct callers of the uniquely named function `name`, resolved through the caller file's imports."""
    def_file = s["defs"][name][0][0]
    stem = Path(def_file).stem
    out = []
    for k, calls in s["calls"].items():
        if k[1].split(".")[-1] == name:
            continue
        f = k[0]
        for kind, base, called in calls:
            if called != name:
                continue
            if kind == "name":
                imp = s["from_imp"][f].get(name)
                if f == def_file or (imp and imp[1] == name and imp[0] in (stem, "")) or name not in COLLIDE and not imp:
                    out.append(k)
                    break
            else:
                mod = s["mod_alias"][f].get(base) or (s["from_imp"][f].get(base, ("", ""))[1] if base in s["from_imp"][f] else "")
                if mod == stem or (base in ("self", "cls") and f == def_file) or name not in COLLIDE:
                    out.append(k)
                    break
    return sorted(set(out))


def short(k: tuple[str, str]) -> str:
    return f"{k[0]}::{k[1].split('.')[-1]}"


def dnt(root: Path) -> dict[str, list[str]]:
    if not (root / "pms.config.json").is_file():
        return {}  # a repository outside the factory declares no roles (ODSF-315)
    cfg = json.loads((root / "pms.config.json").read_text())
    rx = re.compile(r"### DO NOT TOUCH:\s*```[\w]*\n(.*?)```", re.S)
    out = {}
    profiles = cfg.get("role_profiles") or {}
    if not profiles:  # OCO declares a roster and uses the factory's default profile names (project_paths, ODSF-095)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from devkb.process_api import ProcessAPI  # noqa: PLC0415
        profiles = {c: f for c in cfg.get("team_roles") or [] if (f := ProcessAPI._role_file_in(root, cfg, c))}
    for code, fname in profiles.items():
        if not (root / "sdp" / "process" / "roles" / fname).is_file():
            continue
        m = rx.search((root / "sdp" / "process" / "roles" / fname).read_text())
        out[code] = [c for c in (re.split(r"[←#,]", ln)[0].strip() for ln in (m.group(1).splitlines() if m else [])) if c]
    return out


def build(root: Path) -> list[dict]:
    s = scan(root)
    unique = {n: ks[0] for n, ks in s["defs"].items() if len(ks) == 1 and not n.startswith("test_") and not n.startswith("__")}
    rnd = random.Random(310)
    tasks: list[dict] = []

    # RCA: a message raised in exactly one place, by a uniquely named function with real callers and tests.
    counts = collections.Counter(msg for _, msg in s["raises"])
    rca = []
    for key, msg in s["raises"]:
        name = key[1].split(".")[-1]
        if counts[msg] != 1 or len(msg.split()) < 4 or "{" in msg or unique.get(name) != key or is_test_file(key[0]):
            continue
        cs = callers_of(s, name)
        tests = sorted({c[0] for c in cs if is_test_file(c[0])})
        if 2 <= len(cs) <= 10 and tests and any(not is_test_file(c[0]) for c in cs):
            rca.append((key, msg, cs, tests))
    rnd.shuffle(rca)
    for key, msg, cs, tests in rca[:2]:
        name = key[1].split(".")[-1]
        tasks.append({"id": f"RCA-{name}", "stage": "RCA", "kind": "rca", "skill": "devkb-rca",
                      "prompt": (f'A user reports this error: "{msg}". Find the root cause location: the function that raises it, every '
                                 "function that calls that function directly (tests included), and the test files that call it. Answer with one "
                                 'JSON object: {"raiser": "path::function", "callers": ["path::function", ...], "test_files": ["path", ...]}.'),
                      "truth": {"raiser": short(key), "callers": sorted({short(c) for c in cs}), "test_files": tests}})

    # Refactor scope: a uniquely named function whose callers span several files, for a role that may not edit one of them.
    roles = dnt(root)
    picked = {t["id"].split("-", 1)[1] for t in tasks}
    ref = []
    for name, key in unique.items():
        if name in picked or is_test_file(key[0]) or len(name) < 8:
            continue
        cs = callers_of(s, name)
        files = sorted({c[0] for c in cs})
        if not (3 <= len(files) <= 8 and any(is_test_file(f) for f in files)):
            continue
        for role, prefixes in roles.items():
            blocked = sorted(f for f in files if any(f.startswith(p) for p in prefixes))
            if blocked and len(blocked) < len(files) and not any(key[0].startswith(p) for p in prefixes):
                ref.append((name, key, files, role, blocked))
                break
    rnd.shuffle(ref)
    for name, key, files, role, blocked in ref[:2]:
        tasks.append({"id": f"REF-{name}", "stage": "REFACTOR", "kind": "refactor", "skill": "devkb-refactor",
                      "prompt": (f"You work as role {role} and will change the signature of `{name}` (defined in {key[0]}). Before editing, scope the "
                                 "change: list every file that contains a direct caller (tests included), the test files among them, and which of "
                                 f"those files role {role} must not edit according to the DO NOT TOUCH block of its profile in sdp/process/roles. "
                                 'Answer with one JSON object: {"caller_files": [...], "test_files": [...], "blocked_files": [...]}.'),
                      "truth": {"caller_files": files, "test_files": [f for f in files if is_test_file(f)], "blocked_files": blocked}})

    # Onboarding: the most depended-on functions of an area, counting distinct calling functions anywhere.
    for area in ("devkb/", "issue-tools/"):
        rows = []
        for name, key in unique.items():
            if key[0].startswith(area) and not is_test_file(key[0]):
                n = len({c for c in callers_of(s, name)})
                if n:
                    rows.append((n, short(key)))
        rows.sort(key=lambda r: (-r[0], r[1]))
        cutoff = rows[4][0] if len(rows) > 4 else 0
        top = [k for n, k in rows if n >= cutoff]  # the top five, with ties at the fifth place kept
        tasks.append({"id": f"ONB-{area.strip('/')}", "stage": "ONBOARD", "kind": "onboard", "skill": "devkb-onboard",
                      "prompt": (f"You are new to `{area}`. Among the functions defined under `{area}` (excluding test files) whose name is defined "
                                 "only once in this repository, which three have the most distinct calling functions anywhere in the repository, "
                                 'tests included? Answer with one JSON object: {"top": ["path::function", "path::function", "path::function"]}.'),
                      "truth": {"top3": [k for _, k in rows[:3]], "top5": top, "counts": {k: n for n, k in rows[:8]}}})
    return tasks


if __name__ == "__main__":
    t = build(Path(sys.argv[1]))
    json.dump(t, open(sys.argv[2], "w"), indent=1)
    for x in t:
        print(x["id"], {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in x["truth"].items()})
