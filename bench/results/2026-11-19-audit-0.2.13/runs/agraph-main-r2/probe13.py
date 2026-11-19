import sys, time, tempfile, subprocess; sys.path.insert(0, "audit")
from probe import *

def timed(files):
    d = tempfile.mkdtemp(prefix="dk_perf_")
    write(d, files)
    subprocess.run(["git", "init", "-q"], cwd=d)
    subprocess.run(["git", "add", "-A"], cwd=d)
    subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@b.c", "commit", "-qm", "x"], cwd=d)
    t = time.time(); devkb(d, "build"); return time.time() - t

def untyped(n):
    fs = {}
    for i in range(n):
        fs["m%d.py" % i] = "class K%d:\n    def run(self):\n        return 1\n" % i
        fs["u%d.py" % i] = "def use%d(x):\n    return x.run()\n" % i
    return fs

def cpp_untyped(n):
    fs = {}
    for i in range(n):
        fs["m%d.cc" % i] = "class K%d {public: void run();};\nvoid K%d::run(){}\n" % (i, i)
        fs["u%d.cc" % i] = "void use%d(auto x){ x.run(); }\n" % i
    return fs

def many_tests(n):
    fs = {"lib.py": "def core(): pass\n"}
    for i in range(n):
        fs["tests/test_%d.py" % i] = "from lib import core\ndef test_%d():\n    core()\n" % i
    return fs

for name, fn in [("untyped", untyped), ("cppuntyped", cpp_untyped), ("tests", many_tests)]:
    for n in (int(a) for a in sys.argv[1:]):
        print(name, n, "%.1fs" % timed(fn(n)), flush=True)
