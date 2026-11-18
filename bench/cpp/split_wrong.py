#!/usr/bin/env python3
"""split_wrong.py DEVKB_CODE REPO TRUTH.json QUALITY_EXAMPLES.json   (quality.py ... --examples)

Split quality.py's wrong edges: name absent from the caller's body (devkb wrong), truth has another same-named
target from this caller (overload/target pick), or truth has no such call from this caller (truth gap)."""
import json, re, sys, collections
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from devkb import build_symbols
repo, truth, qx = Path(sys.argv[2]), json.load(open(sys.argv[3])), json.load(open(sys.argv[4]))
g = build_symbols.extract(repo)
span = {n.natural_key: (n.props.get("line_start"), n.props.get("line_end")) for n in g.nodes("Symbol")}
defs = truth["defs"]
by_loc = collections.defaultdict(list)
for u, (f, s, e, qn) in defs.items(): by_loc[f].append((s, e, u))
out_names = collections.defaultdict(set)              # caller usr -> callee short names in truth
for a, b in truth["edges"]: out_names[a].add(defs[b][3].rsplit(".", 1)[-1])
lines = {}
res, ex = collections.Counter(), collections.defaultdict(list)
for a, b, src in qx["wrong_examples"]:
    fa, qa = a.split("::", 1); short = b.split("::", 1)[1].rsplit(".", 1)[-1]
    ls, le = span.get(a, (None, None))
    if not ls: res["no span"] += 1; continue
    L = lines.setdefault(fa, (repo / fa).read_text(errors="replace").splitlines())
    body = "\n".join(L[ls - 1:le or ls])
    if not re.search(r"\b" + re.escape(short) + r"\s*(<[^;()]*>)?\s*\(", body):
        k = "name not called in caller body: devkb wrong"
    else:
        callers = {u for s, e, u in by_loc.get(fa, []) if s <= ls <= e or ls <= s <= (le or ls)}
        k = ("truth has another target of that name: target pick" if any(short in out_names[u] for u in callers)
             else "called in body, truth has no such call: truth gap")
    res[k] += 1; ex[k].append(f"{src} | {a} -> {b}")
print(dict(res), "of", len(qx["wrong_examples"]), "sampled (cap 400) of", qx["wrong_edges"])
for k, v in ex.items(): print("##", k); [print("  ", x) for x in v[:4]]
