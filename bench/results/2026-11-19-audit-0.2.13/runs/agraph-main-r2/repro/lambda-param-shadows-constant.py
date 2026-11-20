import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from probe import build, devkb

d, _ = build({"a.py": "LIMIT = 3\n\ndef lam():\n    return lambda LIMIT: LIMIT\n\ndef real():\n    return LIMIT\n"})
rc, out = devkb(d, "pack", "change", "LIMIT")
print(out)
if "a.py::lam" in out or "a.py:4" in out:
    print("DEFECT: the lambda parameter LIMIT (shadowing the constant) is attributed to the module constant")
    print("EXPECTED: only `real` (a.py:7) reaches it")
    sys.exit(1)
print("ok")
