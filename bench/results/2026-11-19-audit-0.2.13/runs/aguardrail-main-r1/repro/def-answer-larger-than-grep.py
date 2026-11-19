import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from _h import fixture, bash, grep

body = "".join("    x%d = %d\n" % (i, i) for i in range(40))
repo = fixture({"m.py": "def finalize(rec):\n" + body + "    return rec\n"})
cmd = 'grep -n "def finalize" m.py'
act, text = bash(repo, cmd)
g = grep(repo, cmd)
print("grep output chars:", len(g), "| hook answer chars:", len(text or ""), "| action:", act)
bad = act == "deny" and len(text) > len(g)
print("DEFECT: the denial answer is larger than grep's own output (a one-line search got a whole body)" if bad else "ok")
sys.exit(1 if bad else 0)
