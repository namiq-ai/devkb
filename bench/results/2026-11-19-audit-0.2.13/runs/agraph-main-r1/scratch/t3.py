import sys, time; sys.path.insert(0, "audit/scratch")
from h import *
d = mk({"a.py": "def f():\n    return 1\n"})
for args in [("pack", "change", "f"), ("pack", "refactor", "f"), ("pack", "error", "boom"), ("pack", "file", "a.py"),
             ("symbol", "f"), ("outline", "a.py"), ("uses", "f"), ("docs", "f"), ("query", "--about", "f"), ("audit",), ("coverage",), ("stats",), ("misses",), ("mcp",)]:
    a = list(args)
    if a[0] == "pack":
        a = ["pack", "--project", d] + a[1:]
    else:
        a = [a[0], "--project", d] + a[1:]
    rc, out = dk(*a)
    print("==", args, rc, "Traceback" in out); print(out[:300])
