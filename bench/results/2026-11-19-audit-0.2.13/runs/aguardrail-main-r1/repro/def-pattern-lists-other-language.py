import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from _h import fixture, bash, grep

repo = fixture({"a.py": "def alpha(x):\n    return x\n", "x.js": "function alpha() { return 1 }\n"})
cmd = 'grep -rn "^def alpha" a.py x.js'
cmd = 'grep -rn "^def alpha" .'
act, text = bash(repo, cmd)
print("grep prints:\n" + grep(repo, cmd))
print("hook:", act, "\n" + str(text))
bad = act == "deny" and "x.js" in text
print("DEFECT: the answer to `^def alpha` lists x.js, which grep does not print; answer is larger than grep" if bad else "ok")
sys.exit(1 if bad else 0)
