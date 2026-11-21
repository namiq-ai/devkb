#!/usr/bin/env python3
"""QB3 (docs/specs/quality-benchmarks.md): does a release audit flag the changes that break a user, and stay quiet about the rest?

Truth: a differential oracle that does not use the graph. For each tag, from `git show TAG:path`, the public surface:
  commands   the `devkb <name>` lines of devkb/cli.py's docstring and its COMMANDS table
  flags      every `--flag` any devkb module passes to add_argument
  tools      the MCP tool names in devkb/mcp_server.py's module-level lists
  nodes      model.NODE_TYPES        verbs   model.VERBS
Between two consecutive tags, an item that disappeared is breaking, one that appeared is additive; no change is internal.
Baselines (what a release note or a reviewer has): the commit subjects (`feat`, `fix`, `!`, "remove", "rename") and the file list (a
public file touched). Each is scored against the oracle: breaking-change recall, precision, and verdict accuracy.

  python bench/quality/qb3_release.py
"""
from __future__ import annotations

import ast
import re
import statistics as st
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_FILES = ("devkb/cli.py", "devkb/mcp_server.py", "devkb/model.py", "devkb/init.py", "devkb/hook.py")


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout


def tags() -> list[str]:
    return sorted(git("tag").split(), key=lambda t: [int(x) for x in re.findall(r"\d+", t)])


def show(tag: str, path: str) -> str:
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"{tag}:{path}"], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def strings(node) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def surface(tag: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    cli = show(tag, "devkb/cli.py")
    try:
        tree = ast.parse(cli)
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])
    doc = ast.get_docstring(tree) or ""
    for line in doc.splitlines():
        m = re.match(r"\s*devkb\s+([\w|-]+)", line)
        if m:
            out |= {("command", c) for c in m[1].split("|") if c}
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COMMANDS" for t in n.targets) and isinstance(n.value, ast.Dict):
            out |= {("command", k.value) for k in n.value.keys if isinstance(k, ast.Constant)}
    files = [f for f in git("ls-tree", "-r", "--name-only", tag, "devkb").split() if f.endswith(".py") and "/" not in f[len("devkb/"):]]
    for f in files:
        try:
            t = ast.parse(show(tag, f))
        except SyntaxError:
            continue
        for n in ast.walk(t):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument":
                out |= {("flag", a) for a in (x.value for x in n.args if isinstance(x, ast.Constant) and isinstance(x.value, str)) if a.startswith("--")}
    try:
        t = ast.parse(show(tag, "devkb/mcp_server.py"))
        for n in t.body:
            if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id.isupper() for x in n.targets) and isinstance(n.value, (ast.List, ast.Tuple)):
                out |= {("tool", s) for s in strings(n.value) if re.fullmatch(r"[a-z][a-z_]+", s)}
    except SyntaxError:
        pass
    try:
        t = ast.parse(show(tag, "devkb/model.py"))
        for n in t.body:
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Tuple):
                for x in n.targets:
                    if isinstance(x, ast.Name) and x.id in ("NODE_TYPES", "VERBS"):
                        out |= {("node" if x.id == "NODE_TYPES" else "verb", s) for s in strings(n.value) if re.fullmatch(r"[A-Za-z_]+", s)}
    except SyntaxError:
        pass
    return out


def oracle(a: str, b: str) -> dict:
    sa, sb = surface(a), surface(b)
    removed, added = sorted(sa - sb), sorted(sb - sa)
    return {"removed": removed, "added": added, "verdict": "breaking" if removed else "additive" if added else "internal"}


def subjects(a: str, b: str) -> list[str]:
    return git("log", f"{a}..{b}", "--pretty=%s%x00%b%x01").split("\x01")


def by_subjects(a: str, b: str) -> str:
    text = "\n".join(subjects(a, b))
    if re.search(r"(^|\n)\w+(\([^)]*\))?!:|BREAKING|\b(remove[sd]?|renam(e|es|ed)|drop(s|ped)?|deprecat\w+)\b", text, re.I):
        return "breaking"
    if re.search(r"(^|\n)\*?\s*(feat|add)\b", text, re.I) or re.search(r"\bfeat(\(|:)", text):
        return "additive"
    return "internal"


def by_files(a: str, b: str) -> str:
    changed = set(git("diff", "--name-only", a, b).split())
    return "breaking" if changed & set(PUBLIC_FILES) else "internal"      # a touched public file: cannot tell breaking from additive


def main() -> None:
    ts = tags()
    rows = []
    for a, b in zip(ts, ts[1:]):
        o = oracle(a, b)
        rows.append({"from": a, "to": b, **o, "subjects": by_subjects(a, b), "files": by_files(a, b)})
    n = len(rows)
    cnt = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("breaking", "additive", "internal")}
    print(f"{n} intervals between {ts[0]} and {ts[-1]}; oracle verdicts: {cnt}")
    for r in rows:
        print(f"  {r['from']:>8} -> {r['to']:<8} {r['verdict']:9} removed {len(r['removed']):2} added {len(r['added']):2}  subjects: {r['subjects']:9} files: {r['files']:9}"
              + (f"  e.g. removed {r['removed'][:2]}" if r["removed"] else ""))
    print("\n| method | breaking recall | breaking precision | verdict accuracy | false calm (an oracle-breaking interval called not breaking) |\n|---|---|---|---|---|")
    for m in ("subjects", "files"):
        tp = sum(1 for r in rows if r["verdict"] == "breaking" and r[m] == "breaking")
        fn = sum(1 for r in rows if r["verdict"] == "breaking" and r[m] != "breaking")
        fp = sum(1 for r in rows if r["verdict"] != "breaking" and r[m] == "breaking")
        acc = st.mean(1.0 if r[m] == r["verdict"] else 0.0 for r in rows)
        print(f"| {m} | {tp}/{tp + fn} | {tp}/{tp + fp if tp + fp else 0} | {acc:.2f} | {fn} |")


if __name__ == "__main__":
    main()
