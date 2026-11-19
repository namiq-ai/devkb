import sys; sys.path.insert(0, "audit")
from probe import *
files = {
    "pkg/__init__.py": "from .impl import work as w2, other as o2\nfrom .deep import deepfn\nfrom pkg.impl import absfn\n",
    "pkg/impl.py": "def work(): return 1\ndef other(): return 2\ndef absfn(): return 3\n",
    "pkg/deep/__init__.py": "from .leaf import deepfn\n",
    "pkg/deep/leaf.py": "def deepfn(): return 4\n",
    "app.py": '''
import pkg
from pkg import w2, o2, deepfn, absfn
from pkg import deep
def a(): return w2()
def b(): return pkg.o2()
def c(): return deepfn()
def d(): return absfn()
def e(): return deep.deepfn()
def f(): return pkg.deep.deepfn()
''',
    "tests/test_app.py": "import app\ndef test_all():\n    app.a(); app.b(); app.c(); app.d(); app.e(); app.f()\n",
}
d, out = build(files)
for q in ["pack change pkg/impl.py::work", "pack change pkg/impl.py::other", "pack change pkg/impl.py::absfn", "pack change pkg/deep/leaf.py::deepfn"]:
    print("=====", q)
    r = devkb(d, *q.split())[1]
    print("\n".join(l for l in r.splitlines() if l.startswith("- `") or "Complete" in l or "Incomplete" in l))
