"""`grep -rn NAME . | head -2` prints 2 lines; the hook treats `head` as the same question (#174) and replaces it with every
call site, so the answer is several times grep's output (SPEC-DKB-007 R5)."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

files = {"lib.py": "def helper(x):\n    return x\n"}
files.update({f"u{i}.py": f"from lib import helper\n\n\ndef go{i}():\n    return helper({i})\n" for i in range(8)})
repo = fixture(files)
cmd = 'grep -rn "helper" . | head -2'
real = grep(repo, cmd)
kind, text = hook(repo, "Bash", cmd)
body = [l for l in text.splitlines() if ".py:" in l]
print(f"grep | head -2 prints {len(real.splitlines())} lines / {len(real)} chars; hook {kind} gives {len(body)} lines / {len(text)} chars")
if kind != "none" and len(body) > len(real.splitlines()):
    print("DEFECT: the answer is larger than the output of the command it replaces")
    sys.exit(1)
print("ok")
