"""`grep -rn helper pkg -A2` (a name with context, not a definition search) gets the definition's body beside it: not the
question asked, and larger than grep's output (SPEC-DKB-007 R5: alongside is never larger than grep)."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

body = "def helper(x):\n" + "".join(f"    v{i} = x + {i}\n" for i in range(20)) + "    return x\n"
repo = fixture({"pkg/lib.py": body, "pkg/use.py": "from pkg.lib import helper\n\n\ndef go():\n    return helper(1)\n"})
cmd = 'grep -rn "helper(" pkg -A2'
real = grep(repo, cmd)
kind, text = hook(repo, "Bash", cmd)
print(f"grep prints {len(real)} chars:\n{real}hook action={kind}, {len(text)} chars:\n{text}")
if kind != "none" and len(text) > len(real):
    print("DEFECT: the answer is", len(text), "chars beside grep's", len(real), "and is the definition body, not the call site")
    sys.exit(1)
print("ok")
