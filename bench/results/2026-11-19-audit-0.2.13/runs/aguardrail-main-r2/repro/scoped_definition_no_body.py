import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

mk = lambda tag: f"def twin(x):\n    y = x + {tag}\n    return y\n"
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": mk(1), "pkg/b.py": mk(2)})
bad = []
for f in ("pkg/a.py", "pkg/b.py"):
    cmd = f'grep -n "def twin" -A3 {f}'
    dec, text = fx.hook(root, {"command": cmd})
    real = fx.grep_lines(root, cmd)
    print(cmd, "->", dec, "| grep prints", len(real), "lines")
    print(text)
    if dec == "deny" and "return y" not in text:
        bad.append(f)
if bad:
    print("DEFECT: the search is denied and the body grep would print (-A3) is not given, with the false reason 'its end is not known':", bad)
    sys.exit(1)
print("ok")
