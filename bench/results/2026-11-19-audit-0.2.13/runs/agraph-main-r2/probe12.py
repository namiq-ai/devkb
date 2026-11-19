import sys, time, tempfile, subprocess; sys.path.insert(0, "audit")
from probe import *

def timed(files):
    d = tempfile.mkdtemp(prefix="dk_perf_")
    write(d, files)
    subprocess.run(["git", "init", "-q"], cwd=d)
    subprocess.run(["git", "add", "-A"], cwd=d)
    subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@b.c", "commit", "-qm", "x"], cwd=d)
    t = time.time(); devkb(d, "build"); return time.time() - t

def typed(n):
    fs = {}
    for i in range(n):
        fs["m%d.py" % i] = "class Svc:\n    def run(self):\n        return 1\n    def stop(self):\n        return 2\ndef use(s: Svc):\n    s.run()\n    s.stop()\n    x = Svc()\n    x.run()\n"
    return fs

def cpp_typed(n):
    fs = {}
    for i in range(n):
        fs["m%d.cc" % i] = "class Svc {public: void run(); void stop();};\nvoid Svc::run(){}\nvoid Svc::stop(){}\nvoid use(Svc* s){ s->run(); Svc x; x.stop(); }\nTEST_F(Fix, T%d){ Svc y; y.run(); }\n" % i
    return fs

def cpp_macros(n):
    fs = {"m.h": "".join("#define M%d(x) f%d(x)\nvoid f%d(int);\n" % (i, i, i) for i in range(n)),
          "m.cc": '#include "m.h"\n' + "".join("void f%d(int){}\nvoid g%d(){ M%d(1); }\n" % (i, i, i) for i in range(n))}
    return fs

def cpp_chain_macros(n):
    s = "#define M0(x) leaf(x)\nvoid leaf(int);\n" + "".join("#define M%d(x) M%d(x); M%d(x)\n" % (i, i - 1, i - 1) if False else "#define M%d(x) M%d(x)\n" % (i, i - 1) for i in range(1, n))
    return {"m.cc": s + "void g(){ M%d(1); }\n" % (n - 1)}

def cpp_many_overloads(n):
    return {"m.cc": "".join("void f(int a%s);\n" % ("".join(", int b%d" % j for j in range(i))) for i in range(1, n)) +
            "".join("void f(int a%s){}\n" % ("".join(", int b%d" % j for j in range(i))) for i in range(1, n)) +
            "void g(){" + "".join("f(1%s);" % (", 2" * i) for i in range(1, n)) + "}\n"}

for name, fn in [("pytyped", typed), ("cpptyped", cpp_typed), ("cppmacros", cpp_macros), ("chainmacros", cpp_chain_macros), ("overloads", cpp_many_overloads)]:
    for n in (int(a) for a in sys.argv[1:]):
        print(name, n, "%.1fs" % timed(fn(n)), flush=True)
