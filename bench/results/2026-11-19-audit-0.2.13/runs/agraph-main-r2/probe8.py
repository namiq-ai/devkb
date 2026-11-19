import sys; sys.path.insert(0, "audit")
from probe import *
files = {
    "pkg/__init__.py": "from .impl import work, Thing\nfrom . import sub\nfrom .sub import *\n",
    "pkg/impl.py": '''
from dataclasses import dataclass
@dataclass
class Thing:
    work: int = 0
    helper: str = ""
def work(x):
    return x
def helper(y):
    return y
def other():
    return helper(1)
''',
    "pkg/sub.py": "def subfn():\n    return 1\n__all__ = ['subfn']\n",
    "app.py": '''
import pkg
from pkg import work, subfn
import pkg.impl as impl
from pkg import sub
def a():
    return work(1)
def b():
    return pkg.work(2)
def c():
    return impl.helper(3)
def d():
    return subfn()
def e():
    return sub.subfn()
def f():
    return pkg.subfn()
def g():
    t = impl.Thing()
    return t.work
''',
    "tests/test_app.py": '''
import app
def test_a(): app.a()
def test_b(): app.b()
def test_c(): app.c()
def test_d(): app.d()
def test_e(): app.e()
def test_f(): app.f()
''',
    "keys.py": '''
import os
def w(d):
    d["alpha"] = 1
    d.setdefault("beta", 2)
    d.update({"gamma": 3})
    del d["delta"]
    x = d.get("epsilon")
    if "zeta" not in d:
        pass
    y = d["eta"]
    for k in ("theta",):
        pass
    os.environ["IOTA"] = "1"
    os.getenv("KAPPA")
    z = {"lam": 1}
    d.pop("mu")
    return d["alpha_beta"]
def alpha_beta(): pass
def alpha(): pass
''',
}
d, out = build(files)
print(out)
for q in sys.argv[1:]:
    print("=====", q)
    print(devkb(d, *q.split())[1][:2200])
