#!/usr/bin/env python3
"""Score a multi-hop answer: F1 of recall and precision, 0..1.   hop_score.py TASKS.json ID ANSWER_FILE REPO_DIR

recall    each callee the task's truth lists counts 1 when its name and its first line are given close together, 0.5 when only the name is.
precision a repository-defined name in the answer is right when the function calls it (any call: `name()`, `self.name()`, `x.name()`),
          wrong when it does not; class names used as qualifiers and the function's own name are not counted.
An earlier version counted as wrong every name outside the truth list, which left out callees whose name several classes share
(`consume_value`) and so marked correct answers down; see docs/analysis/read-tools-benchmark.md."""
import ast, json, re, subprocess, sys
from pathlib import Path

tasks = {t["id"]: t for t in json.load(open(sys.argv[1]))}
tid, ans, repo = sys.argv[2], open(sys.argv[3]).read(), Path(sys.argv[4])
tr = tasks[tid]["truth"]; fn = tr["fn"]
defined, classes, nodes = set(), set(), {}
for f in subprocess.run(["git", "ls-files", "src/click/*.py"], cwd=repo, capture_output=True, text=True).stdout.split():
    for n in ast.walk(ast.parse((repo / f).read_text())):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
            if isinstance(n, ast.ClassDef): classes.add(n.name)
            else: nodes.setdefault(n.name, n)
called = set()
for c in ast.walk(nodes[fn]):
    if isinstance(c, ast.Call):
        x = c.func; name = x.id if isinstance(x, ast.Name) else x.attr if isinstance(x, ast.Attribute) else None
        if name in defined: called.add(name)
hit = 0.0
for c in tr["callees"]:
    ms = [m.start() for m in re.finditer(rf"(?<![\w]){re.escape(c['name'])}(?![\w])", ans)]
    if ms:
        near = any(re.search(rf"(?<![\d.]){c['start']}(?![\d])", ans[max(0, m - 150): m + 150]) for m in ms)
        hit += 1.0 if near else 0.5
rec = hit / len(tr["callees"])
named = {w for w in re.findall(r"[A-Za-z_]\w*", ans) if w in defined and w != fn and w not in classes and not w.startswith("__")}
right = {w for w in named if w in called}; wrong = {w for w in named if w not in called and len(w) > 3}
prec = len(right) / (len(right) + len(wrong)) if right or wrong else 1.0
print(round(2 * rec * prec / (rec + prec), 3) if rec + prec else 0.0)
