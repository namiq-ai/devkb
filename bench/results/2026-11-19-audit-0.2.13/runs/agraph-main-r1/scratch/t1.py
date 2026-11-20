import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"pkg/__init__.py": "from .core import run, helper\n",
"pkg/core.py": '''
import os
LIMIT = 10
HOST, PORT = "h", 80
_inst = None

def run():
    return helper() + LIMIT

def helper():
    return 1

def get():
    global _inst
    if _inst is None:
        _inst = 5
    return _inst

def readhost():
    return HOST

def envk(d):
    if "k" in d:
        pass
    d["k"] += 1
    return os.environ.get("k")

class C:
    LIMIT = 3
    def m(self):
        return LIMIT
''',
"pkg/other.py": '''
from dataclasses import dataclass
@dataclass
class D:
    helper: int = 0
def user():
    return helper()
def helper():
    return 2
''',
"app.py": "import pkg\ndef main():\n    return pkg.run()\n",
"tests/test_a.py": '''
from pkg.core import get, readhost
import app
def test_main():
    assert app.main()
def test_get():
    assert get()
def test_host():
    assert readhost()
''',
}
d = mk(F); print(d)
print(build(d)[1][-300:])
for kind, n in [("change","LIMIT"),("refactor","LIMIT"),("change","HOST"),("refactor","HOST"),("change","PORT"),("change","_inst"),("refactor","_inst"),("change","helper"),("refactor","helper"),("change","run")]:
    print("=====", kind, n); print(dk("pack","--project",d,kind,n)[1][:1500])
print(dk("symbol","--project",d,"k")[1][:1500])
print(dk("uses","--project",d,"k")[1][:1500])
