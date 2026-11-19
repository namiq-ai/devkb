import sys; sys.path.insert(0, "audit/scratch")
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "scratch"))
from h import *
d = mk({"a.py": "def f():\n    return 1\n"})
bad = False
for cmd in ("audit", "coverage"):
    rc, out = dk(cmd, "--project", d)
    print(cmd, "exit", rc); print(out[-400:])
    if "Traceback" in out:
        print("DEFECT: traceback instead of one line saying to build first"); bad = True
    elif "devkb build" not in out:
        print("DEFECT: message does not name `devkb build --project <path>`"); bad = True
print("expected: one line, `no devkb graph ... run devkb build --project PATH first`, for every query command")
sys.exit(1 if bad else 0)
