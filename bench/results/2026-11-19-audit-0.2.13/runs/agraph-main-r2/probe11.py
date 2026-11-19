import sys; sys.path.insert(0, "audit")
from probe import *
files = {
    "cfg.py": "LIMIT = 5\nNAMES = ['a']\n__version__ = '1'\nDEBUG = False\n",
    "pkg/__init__.py": "from cfg import LIMIT\n",
    "a.py": "from cfg import LIMIT\ndef a():\n    return LIMIT\n",
    "b.py": "import cfg\ndef b():\n    return cfg.LIMIT\n",
    "c.py": "from cfg import LIMIT as L\ndef c():\n    return L + 1\n",
    "d.py": "import pkg\ndef d():\n    return pkg.LIMIT\n",
    "e.py": "from cfg import *\ndef e():\n    return LIMIT\n",
    "f.py": "import cfg as C\ndef f():\n    return C.LIMIT\n",
    "g.py": "from cfg import NAMES\ndef g():\n    NAMES.append('x')\n    return [n for n in NAMES]\n",
    "h.py": "def h(LIMIT=5):\n    return LIMIT\ndef i():\n    LIMIT = 3\n    return LIMIT\n",
    "j.py": "from cfg import DEBUG\nclass K:\n    def m(self):\n        if DEBUG:\n            pass\n    x = DEBUG\n",
    "tests/test_all.py": "import a, b, c, d, e, f\ndef test_a(): a.a()\ndef test_b(): b.b()\ndef test_c(): c.c()\ndef test_d(): d.d()\ndef test_e(): e.e()\ndef test_f(): f.f()\n",
}
d, out = build(files)
for q in ["pack change cfg.py::LIMIT", "pack refactor cfg.py::LIMIT", "pack change cfg.py::NAMES", "pack change cfg.py::DEBUG"]:
    print("=====", q)
    r = devkb(d, *q.split())[1]
    print("\n".join(l for l in r.splitlines() if l.strip() and not l.startswith(("This pack", "C/C++", "---", "Built"))))
