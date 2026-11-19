import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from _h import fixture, bash, grep

repo = fixture({"a.py": "def alpha(x):\n    return x + 1\n\n\ndef beta(y):\n    # alpha is called here\n    return alpha(y)\n\n\nNAME = 'alpha'\n",
                "c.py": "def other():\n    return alpha(1)\n"})
cmd = 'grep -rn alpha --include="*.py" .'
act, text = bash(repo, cmd)
print("grep prints:\n" + grep(repo, cmd))
print("hook:", act, "\n" + str(text))
bad = act == "deny" and "alpha is called here" not in text
print("DEFECT: the replacing answer omits the comment line grep prints (a.py:6)" if bad else "ok")
sys.exit(1 if bad else 0)
