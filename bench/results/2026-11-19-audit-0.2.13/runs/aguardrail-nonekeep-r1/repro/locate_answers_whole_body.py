"""SPEC-DKB-007 §3.3: `locate` (`grep -n "def X" f`, no context) is answered with `file:line: signature`. The hook denies
it with the whole body: many times the size of grep's one line."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

src = "def target(a, b):\n" + "".join(f"    step_{i} = a + b + {i}  # explanatory line {i}\n" for i in range(30)) + "    return a\n"
repo = fixture({"m.py": src})
cmd = 'grep -n "def target" m.py'
real = grep(repo, cmd)
kind, text = hook(repo, "Bash", cmd)
print(f"grep prints {len(real)} chars; hook action={kind}, answer {len(text)} chars, {len(text.splitlines())} lines")
if len(text) > len(real) * 2:
    print("DEFECT: a location question got a replacement", len(text) // max(1, len(real)), "times larger than grep's output")
    sys.exit(1)
print("ok")
