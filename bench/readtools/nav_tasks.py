#!/usr/bin/env python3
"""Navigation questions about a Python repository, with exact answers computed from its source.

  nav_tasks.py REPO_DIR OUT.json     (REPO_DIR = a checkout of pallets/click; the questions name click's own symbols)

Each task: id, question, kind (which read tool it exercises), truth (what a correct answer contains)."""
import ast, json, re, subprocess, sys
from pathlib import Path

repo = Path(sys.argv[1])
files = subprocess.run(["git", "ls-files", "src/click/*.py"], cwd=repo, capture_output=True, text=True).stdout.split()
tree = {f: ast.parse((repo / f).read_text()) for f in files}
text = {f: (repo / f).read_text() for f in files}

def find(name, cls=None):
    out = []
    for f, t in tree.items():
        for n in ast.walk(t):
            if cls is None and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
                out.append((f, n.lineno, n.end_lineno))
            if cls and isinstance(n, ast.ClassDef) and n.name == cls:
                for m in n.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == name:
                        out.append((f, m.lineno, m.end_lineno))
    return out

def methods(cls):
    for f, t in tree.items():
        for n in ast.walk(t):
            if isinstance(n, ast.ClassDef) and n.name == cls:
                return f, {m.name: m.lineno for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}

def word_files(w):
    return sorted(f for f, s in text.items() if re.search(rf"\b{re.escape(w)}\b", s))

def call_sites(name):
    """Every tracked text line that mentions the name, except its definition: the question says 'every place'."""
    out = []
    for f in subprocess.run(["git", "grep", "-l", "-w", name], cwd=repo, capture_output=True, text=True).stdout.split():
        for n, line in enumerate((repo / f).read_text(errors="replace").splitlines(), 1):
            if re.search(rf"\b{re.escape(name)}\b", line) and not re.match(rf"\s*(async\s+)?def\s+{name}\b", line):
                out.append([Path(f).name, n])
    return out

rc = find("resolve_command")[0]; wd = find("write_dl", "HelpFormatter")[0]; ev = find("echo_via_pager")[0]
hf_file, hf_methods = methods("HelpFormatter")
getters = sorted({n.name for n in tree["src/click/_compat.py"].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("get_")})
doc = next(f for f in subprocess.run(["git", "ls-files", "docs"], cwd=repo, capture_output=True, text=True).stdout.split() if "shell-completion" in f)
heading = next(l.lstrip("# ").strip() for l in (repo / doc).read_text().splitlines() if l.startswith("#"))
tasks = [
 dict(id="N1", kind="symbol", q="In this repository, give the file and the exact first and last line number of the function `resolve_command` defined under `src/click/`.",
      truth=dict(file=rc[0], start=rc[1], end=rc[2])),
 dict(id="N2", kind="symbol", q="Give the exact first and last line number of the method `HelpFormatter.write_dl` under `src/click/`, and its file.",
      truth=dict(file=wd[0], start=wd[1], end=wd[2])),
 dict(id="N3", kind="symbol-typo", q="Find the function named `echo_via_pagr` (the name may be slightly misspelled) and report its file and the line where it starts.",
      truth=dict(file=ev[0], start=ev[1], end=None)),
 dict(id="N4", kind="outline", q="List every method defined directly in the class `HelpFormatter`, each with its starting line number.",
      truth=dict(file=hf_file, methods=hf_methods)),
 dict(id="N5", kind="uses", q="In which source files under `src/` does the name `FORCED_WIDTH` appear? List the files.",
      truth=dict(files=word_files("FORCED_WIDTH"))),
 dict(id="N6", kind="uses", q="List every place (file basename and line number) where `_expand_args` is referenced, excluding its definition.",
      truth=dict(sites=call_sites("_expand_args"))),
 dict(id="N7", kind="search_docs", q="Which documentation file in this repository explains shell completion, and what is its top-level heading?",
      truth=dict(file=doc, heading=heading)),
 dict(id="N8", kind="symbol-glob", q="List the names of all top-level functions in `src/click/_compat.py` whose name starts with `get_`.",
      truth=dict(names=getters)),
]
json.dump(tasks, open(sys.argv[2], "w"), indent=1)
for t in tasks:
    print(t["id"], t["kind"], json.dumps(t["truth"])[:110])
