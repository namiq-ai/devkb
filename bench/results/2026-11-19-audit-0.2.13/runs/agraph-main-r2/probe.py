import os, subprocess, sys, tempfile, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "bin", "python")


def write(base, files):
    for p, s in files.items():
        fp = os.path.join(base, p)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(textwrap.dedent(s))


def devkb(proj, *args):
    r = subprocess.run([PY, "-m", "devkb.cli", *args, "--project", proj], cwd=ROOT,
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def build(files):
    d = tempfile.mkdtemp(prefix="dk_")
    write(d, files)
    subprocess.run(["git", "init", "-q"], cwd=d)
    subprocess.run(["git", "add", "-A"], cwd=d)
    subprocess.run(["git", "-c","user.name=a","-c","user.email=a@b.c","commit", "-qm","x"], cwd=d)
    rc, out = devkb(d, "build")
    return d, out


if __name__ == "__main__":
    files = {
        "pkg/__init__.py": "from .core import helper\n",
        "pkg/core.py": '''
import os
LIMIT = 5
HOST, PORT = "h", 80
_inst = None

def helper(x):
    return x + LIMIT

def get():
    global _inst
    if _inst is None:
        _inst = object()
    return _inst

def port():
    return PORT

def cfg():
    a = os.environ.get("MYKEY")
    d = {}
    if "k" in d:
        pass
    d["cnt"] += 1
    return d["rec"]

class C:
    LIMIT = 3
    def m(self):
        return LIMIT
''',
        "pkg/user.py": "from pkg import helper\ndef use():\n    return helper(1)\n",
        "tests/test_a.py": '''
from pkg.user import use
from pkg.core import get, port
def test_use():
    assert use()
def test_get():
    get()
def test_port():
    port()
''',
    }
    d, out = build(files)
    print(d, out[-300:])
    for q in sys.argv[1:] or ["pack change LIMIT", "pack refactor LIMIT", "pack refactor helper",
                              "pack change _inst", "pack change PORT", "pack refactor PORT",
                              "symbol HOST", "uses MYKEY", "uses k", "uses cnt", "symbol C.m"]:
        print("=====", q)
        print(devkb(d, *q.split())[1][:1800])
