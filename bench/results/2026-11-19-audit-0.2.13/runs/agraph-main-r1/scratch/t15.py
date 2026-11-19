import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"pkg/core.py": "import os\nLIMIT = 10\ndef run():\n    return LIMIT\n\nclass A:\n    def m(self):\n        return run()\n",
"pkg/use.py": "from .core import run, LIMIT\ndef u():\n    return run() + LIMIT\n",
"tests/test_u.py": "from pkg.use import u\ndef test_u():\n    assert u()\n",
}
d = mk(F); build(d)
for a in (["pack", "file", "pkg/core.py"], ["pack", "file", "nope.py"], ["pack", "file", "pkg"], ["pack", "refactor", "zzz_nothing"], ["pack", "change", "zzz_nothing"], ["pack", "refactor", "re:run"], ["pack", "refactor", "A.m"], ["pack", "refactor", "A::m"], ["pack", "change", ""], ["pack", "refactor", "pkg/core.py::LIMIT"], ["pack", "file", "tests/test_u.py"], ["outline", "pkg/core.py"], ["outline", "nope.py"]):
    rc, out = dk(a[0], "--project", d, *a[1:])
    print("=====", a, rc, "TRACEBACK" if "Traceback" in out else ""); print(out[:900])
