import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

a = "def helper(x):\n    return x\n"
b = ("from pkg.a import helper\n\n\ndef helper_two(x):\n    return helper(x)\n\n\ndef go():\n    return helper_two(1) + helper(2)\n")
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": a, "pkg/b.py": b})
cmd = "grep -rn helper pkg"
dec, text = fx.hook(root, {"command": cmd})
real = fx.grep_lines(root, cmd)
shown = set(l.split(":")[0:2] and ":".join(l.split(":")[:2]) for l in text.splitlines() if l.startswith("pkg/"))
hidden = [l for l in real if ":".join(l.split(":")[:2]) not in shown]
print("decision:", dec)
print("grep prints:", real)
print("answer:\n" + text)
print("hidden:", hidden)
if dec == "deny" and any("helper_two" in l for l in hidden):
    print("DEFECT: the search `grep -rn helper` is replaced by an answer that leaves out lines grep prints because the name is part of a longer one (helper_two)")
    sys.exit(1)
print("ok")
