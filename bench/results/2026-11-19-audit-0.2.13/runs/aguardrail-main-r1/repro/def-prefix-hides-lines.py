import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from _h import fixture, bash, grep

src = "def resolve_file(p):\n    return p\n\n\ndef resolve(q):\n    return q\n\n\ndef caller():\n    return resolve('a')\n"
repo = fixture({"m.py": src})
cmd = 'grep -n "def resolve" m.py'
act, text = bash(repo, cmd)
print("grep prints:\n" + grep(repo, cmd))
print("hook:", act, "\n" + str(text))
bad = act == "deny" and "resolve_file" not in text
print("DEFECT: deny hides the `def resolve_file` line grep prints" if bad else "ok")
sys.exit(1 if bad else 0)
