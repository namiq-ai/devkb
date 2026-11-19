import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

src = ("class A:\n    def m1(self):\n        return 1\n\n    def m2(self):\n        return 2\n\n\n"
       "class B:\n    X = 1\n\n    def m3(self):\n        return 3\n\n\n"
       "def top1():\n    return 1\n\n\ndef top2():\n    return 2\n")
root = fx.make_repo({"pkg/__init__.py": "", "pkg/m.py": src})
cmd = 'grep -n "^class " pkg/m.py'
dec, text = fx.hook(root, {"command": cmd})
real = fx.grep_lines(root, cmd)
body = [l for l in text.splitlines() if l.startswith("L") and "-" in l.split()[0]]
print("grep prints", len(real), "lines:", real)
print("the answer lists", len(body), "symbols:", body)
if len(body) > len(real):
    print("DEFECT: the outline answer to a `^class ` listing carries every function and method of the file, not only the classes grep prints")
    sys.exit(1)
print("ok")
