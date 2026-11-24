"""The guardrail's decisions by intent and outcome since a date (0.2.15 hook analysis).  hook_decisions.py [SINCE]  -> table on stdout."""
import collections, json, os, sys
since = sys.argv[1] if len(sys.argv) > 1 else "2026-11-20T01:59"
rows = [json.loads(l) for l in open(os.path.expanduser("~/.claude/hooks/devkb-guardrail.log")) if l.startswith("{")]
rows = [r for r in rows if r["t"] >= since and "action" in r]
m = collections.defaultdict(collections.Counter)
for r in rows:
    k = r["action"] if r["action"] != "pass-through" else "pt:" + (r.get("reason") or "").split(":")[0]
    m[r.get("intent") or "-"][k] += 1
print(len(rows), "decisions since", since)
for i, c in sorted(m.items(), key=lambda x: -sum(x[1].values())):
    print(f"{i:20s} {sum(c.values()):5d}  {dict(c.most_common(6))}")
