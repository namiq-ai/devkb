import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"pkg/__init__.py": "from .core import run\nfrom .sub import deep\n",
"pkg/sub/__init__.py": "from .impl import deep\n",
"pkg/sub/impl.py": "def deep():\n    return 1\n",
"pkg/core.py": '''
import os
_INST = None
CACHE = {}
MODE = "a"

def get():
    global _INST
    if _INST is None:
        _INST = 5
    return _INST

def setc():
    global CACHE
    CACHE = {}

def run():
    return 1

class K:
    MODE = "b"
    x = MODE
    def f(self):
        return self.x

def uses_mode():
    return MODE

def env():
    return os.environ.get("MODE") or os.environ["MODE"]
''',
"pkg/other.py": '''
from dataclasses import dataclass
@dataclass
class D:
    helper: int = 0
    other: int = helper
def user():
    return helper()
def helper():
    return 2
''',
"pkg/third.py": '''
from dataclasses import dataclass
from .other import helper
@dataclass
class E:
    helper: int = 0
def user3():
    return helper()
''',
"app.py": "import pkg\nfrom pkg import deep\ndef main():\n    pkg.run()\n    return deep()\ndef m2():\n    return pkg.deep()\n",
"tests/test_a.py": '''
from pkg.core import get
import app
def test_main():
    assert app.main()
def test_m2():
    assert app.m2()
def test_get():
    assert get()
''',
}
d = mk(F); print(d)
print(build(d)[1][-300:])
for kind, n in [("change","_INST"),("refactor","_INST"),("change","CACHE"),("change","pkg/core.py::MODE"),("change","pkg/sub/impl.py::deep"),("refactor","pkg/sub/impl.py::deep"),("change","pkg/other.py::helper"),("change","pkg/other.py::D.helper"),("refactor","pkg/other.py::helper")]:
    print("=====", kind, n); print(dk("pack","--project",d,kind,n)[1][:1300])
print(dk("symbol","--project",d,"MODE")[1][:1500])
