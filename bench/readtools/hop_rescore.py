#!/usr/bin/env python3
"""Rescore the multi-hop runs with a truth that does not penalise correct answers.

The first scorer (hop_score.py) counted a repository-defined name in the answer as wrong when it was not in its list of the function's
callees; that list left out every callee whose name is shared by several classes (`consume_value`, `process_value`), so an answer that
named them was marked down. Here the function's *broad* callees are every defined name it calls (a bare call, `self.x()`, `cls.x()`, or
`obj.x()` where `x` is defined in the repository), and a name is wrong only when the function does not call it at all. Class names
that appear only as a qualifier (`Command.format_help`) are not counted either way.

  hop_rescore.py EVAL_DIR REPO_DIR LABEL=GLOB ...      -> per arm: recall, precision, F1; and the paired difference to the first arm"""
import ast, glob, json, random, re, statistics as st, subprocess, sys

E, B = sys.argv[1], sys.argv[2]
tasks = {t["id"]: t for t in json.load(open(E + "/hop-tasks.json"))}
files = subprocess.run(["git", "ls-files", "src/click/*.py"], cwd=B, capture_output=True, text=True).stdout.split()
defined, classes, fn_nodes = set(), set(), {}
for f in files:
    for n in ast.walk(ast.parse(open(B + "/" + f).read())):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
            if isinstance(n, ast.ClassDef): classes.add(n.name)
            else: fn_nodes.setdefault(n.name, n)

def broad(fn):
    called = set()
    for c in ast.walk(fn_nodes[fn]):
        if isinstance(c, ast.Call):
            x = c.func
            name = x.id if isinstance(x, ast.Name) else x.attr if isinstance(x, ast.Attribute) else None
            if name in defined: called.add(name)
    return called

def answer(f):
    for l in open(f):
        try: e = json.loads(l)
        except ValueError: continue
        if e.get("type") == "result": return e.get("result", "") or ""
    return ""

def score(tid, a):
    tr = tasks[tid]["truth"]; fn = tr["fn"]; b = broad(fn)
    want = {c["name"]: c["start"] for c in tr["callees"]}
    hit = 0.0
    for name, start in want.items():
        ms = [m.start() for m in re.finditer(rf"(?<![\w]){re.escape(name)}(?![\w])", a)]
        if ms:
            near = any(re.search(rf"(?<![\d.]){start}(?![\d])", a[max(0, m - 150): m + 150]) for m in ms)
            hit += 1.0 if near else 0.5
    rec = hit / len(want)
    named = {w for w in re.findall(r"[A-Za-z_]\w*", a) if w in defined and w != fn and w not in classes and not w.startswith("__")}
    wrong = {w for w in named if w not in b and len(w) > 3}
    right = {w for w in named if w in b}
    prec = len(right) / (len(right) + len(wrong)) if right or wrong else 1.0
    return rec, prec, (2 * rec * prec / (rec + prec) if rec + prec else 0.0)

arms = {}
for spec in sys.argv[3:]:
    name, pat = spec.split("=", 1)
    arms[name] = {f.split("/")[-1]: score(f.split("-")[-2], answer(f)) for f in sorted(glob.glob(pat))}
base = None
for name, runs in arms.items():
    v = list(runs.values()); m = lambda i: st.mean(x[i] for x in v)
    print(f"{name:34s} n={len(v)} recall {m(0):.3f} precision {m(1):.3f} F1 {m(2):.3f}")
    if base is None: base = runs; continue
    keyed = lambda r: {k.split("-", 1)[1]: x[2] for k, x in r.items()}
    a, b = keyed(base), keyed(runs)
    ks = [k for k in a if k in b]
    d = [b[k] - a[k] for k in ks]
    random.seed(7); boots = sorted(st.mean(random.choice(d) for _ in d) for _ in range(5000))
    print(f"{'':34s} paired F1 difference to the first arm: {st.mean(d):+.3f}  95% interval [{boots[125]:+.3f}, {boots[4875]:+.3f}]  ({len(ks)} pairs)")
