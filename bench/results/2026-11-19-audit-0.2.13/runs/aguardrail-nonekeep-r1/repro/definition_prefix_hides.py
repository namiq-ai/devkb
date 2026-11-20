"""`grep -n "def resolve" f.py` also prints `def resolve_file`; the hook denies it and answers for `resolve` alone."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

repo = fixture({"tools.py": "class T:\n    def resolve_file(self, p):\n        return p\n\n    def resolve(self, q):\n        return q\n"})
cmd = 'grep -n "def resolve" tools.py'
real = grep(repo, cmd)
kind, text = hook(repo, "Bash", cmd)
print("grep prints:\n" + real + f"hook action={kind}:\n" + text)
if kind == "deny" and "resolve_file" in real and "resolve_file" not in text:
    print("DEFECT: grep was denied and its line for resolve_file is nowhere in the answer")
    sys.exit(1)
print("ok")
