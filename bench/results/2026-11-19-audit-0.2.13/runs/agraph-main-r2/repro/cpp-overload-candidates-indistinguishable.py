import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from probe import build, devkb

d, _ = build({
    "a.h": "class A { public:\n  int run(int x);\n  int run(int x, int y);\n};\n",
    "a.cc": '#include "a.h"\nint A::run(int x) { return x; }\nint A::run(int x, int y) { return x + y; }\n',
    "use.cc": '#include "a.h"\nvoid one() { A a; a.run(1); }\nvoid two() { A a; a.run(1, 2); }\n',
})
bad = []
for kind in ("change", "refactor"):
    rc, out = devkb(d, "pack", kind, "A::run")
    print("$ pack", kind, "A::run\n" + out)
    cands = [l for l in out.splitlines() if l.startswith("- `")]
    if len(cands) != len(set(cands)):
        bad.append(kind + ": candidates identical " + repr(cands))
rc, out = devkb(d, "pack", "change", "a.cc::A.run")
print(out)
if "use.cc::two" in out and "int A::run(int x) {" in out:
    bad.append("the 1-arg overload (a.cc:2) is reported as reached by two(), which calls run(1, 2)")
if bad:
    print("DEFECT:", *bad, sep="\n  ")
    print("EXPECTED: candidates distinguishable (line or signature) and arity-correct callers per overload")
    sys.exit(1)
print("ok")
