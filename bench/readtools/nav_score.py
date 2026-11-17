#!/usr/bin/env python3
"""Score the final answer of a navigation run against the task's truth. 1.0 = fully correct.
  nav_score.py TASKS.json ID ANSWER_TEXT_FILE"""
import json, re, sys
tasks = {t["id"]: t for t in json.load(open(sys.argv[1]))}
t = tasks[sys.argv[2]]; ans = open(sys.argv[3]).read(); tr = t["truth"]

def f1(got, want):
    got, want = set(got), set(want)
    if not got or not want:
        return 0.0
    p, r = len(got & want) / len(got), len(got & want) / len(want)
    return 2 * p * r / (p + r) if p + r else 0.0

nums = lambda s: {int(x) for x in re.findall(r"(?<![\w.])(\d{1,5})(?!\w|\.\d)", s)}   # a number may end a sentence
base = lambda p: p.rsplit("/", 1)[-1]
k = t["id"]
if k in ("N1", "N2"):
    n = nums(ans); score = (0.4 if tr["file"] in ans or base(tr["file"]) in ans else 0) + (0.3 if tr["start"] in n else 0) + (0.3 if tr["end"] in n else 0)
elif k == "N3":
    n = nums(ans); score = (0.5 if base(tr["file"]) in ans else 0) + (0.5 if tr["start"] in n else 0)
elif k == "N4":
    got = {(m, int(l)) for m, l in re.findall(r"`?(\w+)`?\D{1,12}?(\d{2,4})", ans) if m in tr["methods"]}
    want = {(m, l) for m, l in tr["methods"].items()}
    score = f1(got, want)
elif k == "N5":
    score = f1({f for f in tr["files"] if f in ans or base(f) in ans} | {m for m in re.findall(r"src/click/\w+\.py", ans) if m not in tr["files"]}, tr["files"])
elif k == "N6":
    want = {(b, l) for b, l in tr["sites"]}
    got = set(); cur = None            # every number on a line belongs to the file name before it, so `core.py: 45, 1561` gives both sites
    for line in ans.splitlines():
        for tok in re.finditer(r"(\w+\.py)|(?<![\w.])(\d{1,5})(?![\w])", line):
            if tok.group(1): cur = tok.group(1)
            elif cur: got.add((cur, int(tok.group(2))))
    score = f1(got, want)
elif k == "N7":
    score = (0.6 if tr["file"] in ans else 0) + (0.4 if tr["heading"].lower() in ans.lower() else 0)
elif k == "N8":
    got = set(re.findall(r"\bget_\w+", ans)); score = f1(got, tr["names"])
else:
    score = 0
print(round(score, 3))
