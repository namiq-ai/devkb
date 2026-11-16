"""Pick chain questions from a compiler call graph (bench/roslyn_truth): production targets with 6-30 production
callers, reached at depth 2 or more, whose name is one method family in its type.

  python bench/cs_pick_from_roslyn.py REPO_CLONE TRUTH.json N [--seed 2032] [--exclude Name,...]
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cs_truth_from_roslyn import closure, is_production  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("repo")
ap.add_argument("truth")
ap.add_argument("n", type=int)
ap.add_argument("--seed", type=int, default=2032)
ap.add_argument("--exclude", default="")
a = ap.parse_args()
g = json.loads(Path(a.truth).read_text())
defs = g["defs"]
callers, bases = defaultdict(set), defaultdict(set)
for x, y in g["edges"]:
    callers[y].add(x)
for i, b in g["dispatch"]:
    bases[i].add(b)
fam = defaultdict(set)
for i, (f, _s, _e, qn) in defs.items():
    fam[(f, qn)].add(i)
cands = [(f, qn) for (f, qn), ids in fam.items() if is_production(f) and not qn.endswith(".ctor")
         and qn.split(".")[-1] not in a.exclude.split(",")]
random.seed(a.seed)
random.shuffle(cands)
out = []
for f, qn in cands:
    starts = fam[(f, qn)]
    reach = closure(starts, callers, bases, {}, False)
    prod = {defs[i][3] for i in reach if i in defs and is_production(defs[i][0])}
    direct = {defs[i][3] for s in starts for i in callers.get(s, ()) if i in defs and is_production(defs[i][0])}
    if 6 <= len(prod) <= 30 and len(prod) > len(direct):          # a chain: some callers are indirect
        out.append({"repo": a.repo, "target": qn, "name": qn.split(".")[-1], "file": f, "line": defs[next(iter(starts))][1],
                    "truth": sorted(prod), "uncertain": [], "tests": []})
        if len(out) >= a.n:
            break
print(json.dumps(out, indent=1))
