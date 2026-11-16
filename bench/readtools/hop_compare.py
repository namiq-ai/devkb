#!/usr/bin/env python3
"""hop_compare.py EVAL_DIR TASKS.json REPO_DIR LABEL=GLOB ... : score, turns, calls, context, cache writes, cost, tools per run, per arm."""
import collections, glob, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import cost_breakdown as cb
tasks, repo = sys.argv[2], sys.argv[3]
for spec in sys.argv[4:]:
    name, pat = spec.split("=", 1); fs = sorted(glob.glob(pat)); n = len(fs); bs = [cb.breakdown(f) for f in fs]; sc = []; tools = collections.Counter(); turns = 0
    for f in fs:
        ans = ""
        for l in open(f):
            try: e = json.loads(l)
            except ValueError: continue
            if e.get("type") == "assistant":
                for x in e["message"]["content"]:
                    if x.get("type") == "tool_use": tools[x["name"].replace("mcp__devkb__", "devkb:")] += 1
            if e.get("type") == "result": ans = e.get("result", "") or ""; turns += e.get("num_turns", 0)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as t: t.write(ans)
        s = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "hop_score.py"), tasks, f.split("-")[-2], t.name, repo], capture_output=True, text=True).stdout.strip()
        sc.append(float(s) if s else 0.0); os.unlink(t.name)
    m = lambda xs: sum(xs) / len(xs)
    print(f"{name:26s} n={n} score {m(sc):.3f} | turns {turns / n:.2f} | model calls {m([len(b['rows']) for b in bs]):.2f} | first ctx {m([b['ctx'][0] for b in bs]) / 1000:.1f}k | cache-write {m([sum(x['cw'] for x in b['rows']) for b in bs]) / 1000:.1f}k | cost ${m([b['cost'] for b in bs]):.4f}")
    print("     tools/run:", {k: round(v / n, 2) for k, v in tools.items()})
