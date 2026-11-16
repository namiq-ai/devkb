#!/usr/bin/env python3
"""Score a multi-hop answer. hop_score.py TASKS.json ID ANSWER_FILE REPO_DIR -> score in [0,1].
Each truth callee counts 1 when its name and its first line are both given close together, 0.5 when only the name is; precision is
penalised by repository-defined names the answer lists that are not callees."""
import ast, json, re, subprocess, sys
from pathlib import Path
tasks = {t["id"]: t for t in json.load(open(sys.argv[1]))}
t = tasks[sys.argv[2]]; ans = open(sys.argv[3]).read(); repo = Path(sys.argv[4]); tr = t["truth"]
files = subprocess.run(["git", "ls-files", "src/click/*.py"], cwd=repo, capture_output=True, text=True).stdout.split()
defined = set()
for f in files:
    for n in ast.walk(ast.parse((repo / f).read_text())):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
hit = 0.0
for c in tr["callees"]:
    ms = [m.start() for m in re.finditer(rf"(?<![\w]){re.escape(c['name'])}(?![\w])", ans)]
    if not ms:
        continue
    near = any(re.search(rf"(?<![\d.]){c['start']}(?![\d])", ans[max(0, m - 150): m + 150]) for m in ms)
    hit += 1.0 if near else 0.5
want = {c["name"] for c in tr["callees"]}
claimed = {w for w in re.findall(r"`?([A-Za-z_]\w*)`?", ans) if w in defined and w != tr["fn"] and not w.startswith("__")}
extra = {w for w in claimed if w not in want and len(w) > 3}
rec = hit / len(want); prec = len(want & claimed) / max(1, len(want & claimed) + len(extra))
print(round(2 * rec * prec / (rec + prec), 3) if rec + prec else 0.0)
