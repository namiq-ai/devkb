import sys, json, os; sys.path.insert(0, "audit/scratch")
from h import *
exec(open("audit/scratch/t6.py").read().split("d = mk(F)")[0].split("from h import *")[1])
d = mk(F); build(d)
for f in ("symbols-nodes.jsonl", "symbols-edges.jsonl"):
    for l in open(os.path.join(d, ".devkb", f)):
        if "get" in l or "put" in l:
            print(f[:9], l.strip()[:300])
