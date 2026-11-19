"""SPEC-DKB-007 R7/§3.5: each decision line logs the graph question asked (`uses`, `symbol`, `outline`, `none`). The hook
logs `pack refactor` for a call-sites answer built from `uses`, and `none` for an outline answer."""
import json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook

repo = fixture({"m.py": "def helper(x):\n    return x\n\n\ndef go():\n    return helper(1)\n"})
log = repo.parent / "home" / ".claude" / "hooks" / "devkb-guardrail.log"
bad = []
for cmd, want in (('grep -rn "helper" .', "uses"), ('grep -n "^def " m.py', "outline")):
    kind, text = hook(repo, "Bash", cmd)
    row = json.loads(log.read_text().splitlines()[-1])
    print(f"{cmd!r}: hook {kind}; answer built from {want}; logged intent={row['intent']} question={row['question']!r}")
    if want not in row["question"]:
        bad.append(cmd)
if bad:
    print("DEFECT: the question logged is not the graph question the answer came from, for", bad)
    sys.exit(1)
print("ok")
