import sys, time, tempfile, subprocess; sys.path.insert(0, "audit")
from probe import *

def timed(name, files):
    d = tempfile.mkdtemp(prefix="dk_perf_")
    write(d, files)
    subprocess.run(["git", "init", "-q"], cwd=d)
    subprocess.run(["git", "add", "-A"], cwd=d)
    subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@b.c", "commit", "-qm", "x"], cwd=d)
    t = time.time(); devkb(d, "build"); return time.time() - t

def consts_used(n):
    src = "".join("C%d = %d\n" % (i, i) for i in range(n))
    src += "".join("def f%d():\n    return C%d\n" % (i, i) for i in range(n))
    return {"m.py": src}

def consts_used_many(n):
    # every function reads one shared constant
    src = "SHARED = 1\n" + "".join("def f%d():\n    return SHARED\n" % i for i in range(n))
    return {"m.py": src}

def same_method(n):
    fs = {}
    for i in range(n):
        fs["m%d.py" % i] = "class K%d:\n    def run(self):\n        return 1\n    def go(self):\n        return self.run()\n" % i
    fs["u.py"] = "".join("from m%d import K%d\n" % (i, i) for i in range(n)) + "def u():\n" + "".join("    k%d = K%d()\n    k%d.run()\n" % (i, i, i) for i in range(n))
    return fs

def many_fields(n):
    return {"m.py": "from dataclasses import dataclass\n@dataclass\nclass D:\n" + "".join("    f%d: int = 0\n" % i for i in range(n)) +
            "def go(d: D):\n" + "".join("    d.f%d\n" % i for i in range(n))}

def string_keys(n):
    return {"m.py": "def f(d):\n" + "".join("    d['k%d'] = d['k%d']\n" % (i, i) for i in range(n))}

def many_calls_one_func(n):
    return {"m.py": "def g(): pass\ndef f():\n" + "    g()\n" * n}

def many_globals(n):
    return {"m.py": "".join("G%d = None\ndef s%d():\n    global G%d\n    G%d = 1\n    return G%d\n" % (i, i, i, i, i) for i in range(n))}

for name, fn in [("consts_used", consts_used), ("shared", consts_used_many), ("same_method", same_method),
                 ("fields", many_fields), ("strkeys", string_keys), ("manycalls", many_calls_one_func), ("globals", many_globals)]:
    for n in (int(a) for a in sys.argv[1:]):
        print(name, n, "%.1fs" % timed(name, fn(n)), flush=True)
