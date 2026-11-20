import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

src = "def big(x):\n" + "".join(f"    y{i} = x + {i}\n" for i in range(120)) + "    return x\n"
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": src})
cmd = 'grep -n "def big" -A10 pkg/a.py'
dec, text = fx.hook(root, {"command": cmd})
real = fx.grep_lines(root, cmd)
print("decision:", dec, "| grep would print", len(real), "lines")
print(text)
if dec == "deny" and "y0 = x + 0" not in text:
    print("DEFECT: grep -A10 is denied and answered with a location only ('Body not shown'); the 10 lines it asked for are hidden "
          "(the agent must re-run the search)")
    sys.exit(1)
print("ok")
