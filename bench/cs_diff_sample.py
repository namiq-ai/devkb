"""Edges a resolver change added and removed, sampled for checking by hand.

  python bench/cs_diff_sample.py REPO OLD_REF N   (OLD_REF: a git ref of devkb whose csharp_symbols.py is the baseline)
"""
import importlib.util
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import csharp_symbols as new  # noqa: E402

repo, ref, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
src = subprocess.run(["git", "show", f"{ref}:devkb/csharp_symbols.py"], cwd=ROOT, capture_output=True, text=True,
                     check=True).stdout
old = importlib.util.module_from_spec(importlib.util.spec_from_loader("old", loader=None))
exec(src, old.__dict__)
osyms, a = old.extract(repo)
nsyms, b = new.extract(repo)
lines = {s["key"]: s["line_start"] for s in nsyms + osyms}
A = {(c["caller"], c["callee"]): c for c in a}
B = {(c["caller"], c["callee"]): c for c in b}


def src_line(rel, ln):
    try:
        return (repo / rel).read_text(errors="replace").splitlines()[ln - 1].strip()[:140]
    except (OSError, IndexError):
        return "?"


print(f"{repo.name}: {len(A)} edges before, {len(B)} after; removed {len(A.keys() - B.keys())}, added {len(B.keys() - A.keys())}")
random.seed(2032)
for label, keys, side in (("REMOVED", sorted(A.keys() - B.keys()), A), ("ADDED", sorted(B.keys() - A.keys()), B)):
    pick = random.sample(keys, min(n, len(keys)))
    print(f"\n## {label} (sample {len(pick)} of {len(keys)})")
    for i, k in enumerate(sorted(pick, key=lambda k: (side[k]["rel"], side[k]["line"])), 1):
        c = side[k]
        callee_rel = c["callee"].split("::")[0]
        print(f"{i:2d}. {c['caller'].split('::')[1]} -> {c['callee'].split('::')[1]}")
        print(f"    call {c['rel']}:{c['line']}: {src_line(c['rel'], c['line'])}")
        print(f"    def  {callee_rel}:{lines.get(c['callee'], 0)}: {src_line(callee_rel, lines.get(c['callee'], 0))}")
