#!/usr/bin/env python3
"""Compare a graph_info.py run with a baseline: node and edge counts by type, graph size and build time.

  graph_compare.py BASELINE.json NEW.json [--count-tol 0.02] [--size-tol 0.10] [--time-tol 0.25]

Exit 1 when a total or a per-type count moved by more than --count-tol (default 2%) or the size by more than --size-tol, or a build took
more than --time-tol longer (default 25%). A moved count is not always a defect: a new feature adds edges (state it in the release notes
and write a new baseline); a count that FALLS with no change meant to remove it is usually the defect. `STEP` edges (flow tracing) vary
by about 1,300 between any two Zephyr builds and are excluded from the comparison."""
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
arg = lambda k, d: float(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
ct, st, tt = arg("--count-tol", 0.02), arg("--size-tol", 0.10), arg("--time-tol", 0.25)
IGNORE = {"STEP"}
bad = []
print(f"baseline {a['label']} (devkb {a['code'][:8]})  against  {b['label']} (devkb {b['code'][:8]})\n")
print("| Repository | Nodes | Edges | Graph MB | Build s | Moved types |\n|---|---|---|---|---|---|")
for n, x in a["repos"].items():
    y = b["repos"].get(n)
    if not y:
        bad.append(f"{n}: missing from the new run"); continue
    if x["commit"] != y["commit"]:
        print(f"| {n} | repository commit differs ({x['commit'][:8]} / {y['commit'][:8]}): not comparable | | | | |"); continue
    moved = []
    for kind, ka, kb in (("node", x["node_types"], y["node_types"]), ("edge", x["edge_verbs"], y["edge_verbs"])):
        for t in sorted(set(ka) | set(kb)):
            if t in IGNORE: continue
            u, v = ka.get(t, 0), kb.get(t, 0)
            if abs(v - u) > max(5, ct * u):
                moved.append(f"{t} {u:,}→{v:,}"); bad.append(f"{n} {kind} {t} {u}→{v}")
    ex = lambda r: r["edges"] - r["edge_verbs"].get("STEP", 0)
    if abs(ex(y) - ex(x)) > ct * ex(x): bad.append(f"{n} edges {ex(x)}→{ex(y)}")
    if abs(y["nodes"] - x["nodes"]) > ct * x["nodes"]: bad.append(f"{n} nodes {x['nodes']}→{y['nodes']}")
    if y["graph_mb"] > x["graph_mb"] * (1 + st) + 0.5: bad.append(f"{n} size {x['graph_mb']}→{y['graph_mb']} MB")
    if y["build_secs"] > x["build_secs"] * (1 + tt) + 1.0: bad.append(f"{n} build {x['build_secs']}→{y['build_secs']} s")
    print(f"| {n} | {x['nodes']:,} → {y['nodes']:,} | {x['edges']:,} → {y['edges']:,} | {x['graph_mb']} → {y['graph_mb']} | {x['build_secs']} → {y['build_secs']} | {'; '.join(moved) or 'none'} |")
print("\n" + ("OUTSIDE THE TOLERANCES: " + "; ".join(bad) if bad else f"within the tolerances (counts {ct:.0%}, size {st:.0%}, build time {tt:.0%})"))
sys.exit(1 if bad else 0)
