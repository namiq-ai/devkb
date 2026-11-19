import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fx

body = "def helper(x):\n    return x * 2\n\n\n" + "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(3))
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": body})
cmd = "grep -rn helper pkg | head -1"
dec, text = fx.hook(root, {"command": cmd})
real = fx.grep_lines(root, cmd)
n_ans = len([l for l in text.splitlines() if l.startswith("pkg/")])
print("decision:", dec, "| grep prints", len(real), "line(s); the answer carries", n_ans, "lines")
print(text)
if dec == "deny" and n_ans > len(real):
    print("DEFECT: the answer is larger than what the command would print (head -1 asked for one line)")
    sys.exit(1)
print("ok")
