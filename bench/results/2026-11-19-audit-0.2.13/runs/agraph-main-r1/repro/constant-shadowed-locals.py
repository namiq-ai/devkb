import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch"))
from h import *
SHADOWS = {
    "p_lambda": "    f = lambda LIMIT: LIMIT\n    return f(1)\n",
    "p_except": "    try:\n        pass\n    except Exception as LIMIT:\n        return LIMIT\n",
    "p_with": "    with open('x') as LIMIT:\n        return LIMIT\n",
    "p_for": "    for LIMIT in range(3):\n        return LIMIT\n",
    "p_walrus": "    if (LIMIT := 5):\n        return LIMIT\n",
    "p_nested": "    def inner(LIMIT):\n        return LIMIT\n    return inner\n",
    "p_match": "    match 1:\n        case LIMIT:\n            return LIMIT\n",
    "p_unpack": "    LIMIT, other = 1, 2\n    return LIMIT\n",
    "p_import": "    from os import sep as LIMIT\n    return LIMIT\n",
    "p_ann": "    LIMIT: int = 4\n    return LIMIT\n",
    "p_del_global_free": "    return 1\n",
}
src = "LIMIT = 10\n" + "".join(f"def {k}():\n{v}" for k, v in SHADOWS.items())
d = mk({"m.py": src})
build(d)
out = dk("pack", "--project", d, "change", "m.py::LIMIT")[1]
wrong = [k for k in SHADOWS if f"m.py::{k}`" in out]
print("functions that bind their own LIMIT yet are listed as reaching the module constant:", wrong)
print("expected: []  (a local, parameter, except/with/for/walrus/match/import binding shadows the module constant)")
sys.exit(1 if wrong else 0)
