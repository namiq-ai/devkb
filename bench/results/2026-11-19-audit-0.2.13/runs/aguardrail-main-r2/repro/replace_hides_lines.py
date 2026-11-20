import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

# a helper defined once and used 6 times (so `uses` caps its hits), with a docstring line and the def line grep prints
body = "def helper(x):\n    \"\"\"helper doubles x.\"\"\"\n    return x * 2\n\n\n"
body += "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(6))
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": body})
cmd = "grep -rn helper pkg"
dec, text = fx.hook(root, {"command": cmd})
real = [l for l in fx.grep_lines(root, cmd) if "Binary" not in l and "pycache" not in l]
shown = {l.split(":", 2)[1] for l in text.splitlines() if l.count(":") >= 2 and l.split(":")[0].endswith(".py")}
missing = [l for l in real if l.split(":")[1] not in shown]
print("decision:", dec)
print("grep prints", len(real), "lines; the answer shows", len(shown))
print("lines grep prints that the replacement hides:", missing)
print(text)
if dec == "deny" and missing:
    print("DEFECT: the search is replaced by an answer that hides lines grep would print (e.g. the def line)")
    sys.exit(1)
print("ok")
