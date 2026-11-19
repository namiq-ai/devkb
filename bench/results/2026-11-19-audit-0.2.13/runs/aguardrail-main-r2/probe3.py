import sys, os, json, subprocess, time
sys.path.insert(0, "audit/repro")
import fx
body = "def helper(x):\n    return x * 2\n\n\n" + "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(3))
root = fx.make_repo({"pkg/__init__.py": "", "pkg/a.py": body, "pkg/c.py": "from pkg.a import helper\n\n\ndef g():\n    return helper(9)\n"})
time.sleep(1.1)
# edit tracked file: add a caller
with open(root / "pkg/c.py", "a") as f:
    f.write("\n\ndef h():\n    return helper(10)\n")
for c in sys.argv[1:]:
    d, x = fx.hook(root, {"command": c})
    print("===", c, "->", d)
    print(x[:600])
    print("--- real:")
    print("\n".join(fx.grep_lines(root, c)))
