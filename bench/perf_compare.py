#!/usr/bin/env python3
"""perf_compare.py BASE.json NEW.json [--max-build 1.25] [--max-query 1.5] : a table of build time, peak memory, graph size and query
latency, new against base, and a non-zero exit when a ratio passes its limit (build time and query latency; memory and size are reported)."""
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
mb = float(sys.argv[sys.argv.index("--max-build") + 1]) if "--max-build" in sys.argv else 1.25
mq = float(sys.argv[sys.argv.index("--max-query") + 1]) if "--max-query" in sys.argv else 1.5
med = lambda xs: sorted(xs)[len(xs) // 2]
bad = []
print(f"{a['label']} (base) against {b['label']} (new); ratio = new / base\n")
print("| Repository | Files | Build s (base → new) | Ratio | Peak MB (base → new) | Graph MB (base → new) |\n|---|---|---|---|---|---|")
for n, ra in a["repos"].items():
    rb = b["repos"].get(n)
    if not rb: continue
    ta, tb = med([x["secs"] for x in ra["build"]]), med([x["secs"] for x in rb["build"]]); r = tb / ta
    if r > mb: bad.append(f"{n} build {r:.2f}x")
    print(f"| {n} | {ra['files']} | {ta:.1f} → {tb:.1f} | {r:.2f}x | {med([x['peak_mb'] for x in ra['build']])} → {med([x['peak_mb'] for x in rb['build']])} | {ra['graph_mb']} → {rb['graph_mb']} |")
print("\n| Repository | Query | Base s | New s | Ratio |\n|---|---|---|---|---|")
for n, ra in a["repos"].items():
    rb = b["repos"].get(n)
    if not rb: continue
    for q, x in ra["queries"].items():
        y = rb["queries"].get(q)
        if not y: continue
        r = y["median_s"] / x["median_s"] if x["median_s"] else 0
        flag = " **slower**" if r > mq and y["median_s"] - x["median_s"] > 0.05 else ""
        if flag: bad.append(f"{n} {q} {r:.2f}x")
        print(f"| {n} | {q} | {x['median_s']:.3f} | {y['median_s']:.3f} | {r:.2f}x{flag} |")
    for q in rb["queries"]:
        if q not in ra["queries"]:
            print(f"| {n} | {q} | (new) | {rb['queries'][q]['median_s']:.3f} | |")
print("\nlimits: build " + f"{mb}x, query {mq}x and 0.05 s; " + ("EXCEEDED: " + "; ".join(bad) if bad else "none exceeded"))
sys.exit(1 if bad else 0)
