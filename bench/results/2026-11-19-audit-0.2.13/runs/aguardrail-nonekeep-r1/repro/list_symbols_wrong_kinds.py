"""`grep -n "^def " f.py` asks for the top-level functions. The outline answer beside it lists constants, classes, fields
and methods too, so it is larger than grep's output and answers another question (SPEC-DKB-007 R5)."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _fx import fixture, hook, grep

src = ("A = 1\nB = 2\nC = 3\nD = 4\n\n\nclass K:\n    x: int\n    y: int\n\n    def m(self):\n        return 1\n\n\n"
       "def one():\n    return 1\n\n\ndef two():\n    return 2\n")
repo = fixture({"m.py": src})
cmd = 'grep -n "^def " m.py'
real = grep(repo, cmd)
kind, text = hook(repo, "Bash", cmd)
print("grep prints:\n" + real + f"hook action={kind}, {len(text)} chars vs grep {len(real)}:\n" + text)
extra = [l for l in text.splitlines() if " constant " in l or " field " in l or " class " in l or " method " in l]
if extra or len(text) > len(real):
    print("DEFECT: the answer lists", len(extra), "symbols that are not top-level functions; it is larger than grep's output")
    sys.exit(1)
print("ok")
