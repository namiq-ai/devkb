#!/usr/bin/env python3
"""Multi-hop navigation questions: for a function, every function it calls directly that is defined in the repository, with each
one's file and first line. Answering takes one lookup of the function and one per callee. Truth from the AST.

  hop_tasks.py REPO_DIR OUT.json   (REPO_DIR = a checkout of pallets/click)"""
import ast, builtins, collections, json, subprocess, sys
from pathlib import Path

repo = Path(sys.argv[1])
files = subprocess.run(["git", "ls-files", "src/click/*.py"], cwd=repo, capture_output=True, text=True).stdout.split()
defs = collections.defaultdict(list)          # short name -> [(file, start, end, qualified)]
nodes = {}
for f in files:
    t = ast.parse((repo / f).read_text())
    def walk(body, prefix):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}{n.name}"
                defs[n.name].append((f, n.lineno, n.end_lineno, q)); nodes[(f, q)] = n
                walk(n.body, q + ".")
    walk(t.body, "")
unique = {k: v[0] for k, v in defs.items() if len(v) == 1 and not k.startswith("__")}
cands = []
for (f, q), n in nodes.items():
    if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) or n.name.startswith("__") or len(defs[n.name]) != 1:
        continue
    called = set()
    for c in ast.walk(n):
        if isinstance(c, ast.Call):
            fn = c.func
            # a call the repository itself defines: `name()` or `self.name()` / `cls.name()`; never `obj.name()` on a library object
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in ("self", "cls") else None
            if name and name in unique and name != n.name and not hasattr(builtins, name) and name not in ("read", "write", "open", "close", "get", "add"):
                called.add(name)
    if 3 <= len(called) <= 7 and (n.end_lineno - n.lineno) >= 12:
        cands.append((len(called), q, f, n, sorted(called)))
cands.sort(key=lambda c: (-c[0], c[1]))
picked, used_files = [], collections.Counter()
for k, q, f, n, called in cands:
    if used_files[f] < 2 and len(picked) < 8:
        picked.append((q, f, n, called)); used_files[f] += 1
tasks = []
for i, (q, f, n, called) in enumerate(picked, 1):
    tasks.append(dict(id=f"M{i}", kind="multi-hop",
                      q=f"Find the function `{n.name}` defined under `src/click/`. List every function or method defined in `src/click/` that `{n.name}` calls directly, each with its file and first line number. Do not include library or builtin calls.",
                      truth=dict(fn=n.name, file=f, callees=[dict(name=c, file=unique[c][0], start=unique[c][1]) for c in called])))
json.dump(tasks, open(sys.argv[2], "w"), indent=1)
for t in tasks:
    print(t["id"], t["truth"]["fn"], len(t["truth"]["callees"]), [c["name"] for c in t["truth"]["callees"]])
