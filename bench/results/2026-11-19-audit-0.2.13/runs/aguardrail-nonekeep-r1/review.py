import json, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
repo = root / "audit" / "_rp"
d = json.load(open(root / "audit" / "replay_out.json"))
n = 0
for x in d:
    o = x["out"]
    if not o:
        continue
    h = o["hookSpecificOutput"]
    ans = h.get("permissionDecisionReason") or h.get("additionalContext", "")
    if ans.startswith("devkb guardrail:"):
        continue
    kind = "DENY" if h.get("permissionDecision") == "deny" else "ALONG"
    gsize = None
    if x["tool"] == "Bash":
        try:
            p = subprocess.run(x["input"]["command"], shell=True, cwd=repo, capture_output=True, text=True, timeout=20)
            gsize = len(p.stdout)
        except Exception:
            pass
    n += 1
    cmd = x["input"].get("command") or json.dumps(x["input"])
    print(f"=== #{x['i']} {kind} ans={len(ans)} grep={gsize}\n  CMD: {cmd[:400]}\n  ANS: {ans[:500]!r}")
print(n)
