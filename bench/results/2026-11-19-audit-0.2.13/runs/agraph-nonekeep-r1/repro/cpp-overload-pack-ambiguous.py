import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _h

d = _h.make({
 "a.h": "struct Foo { int bar(int x); int bar(int x, int y); };\n",
 "a.cc": '#include "a.h"\nint Foo::bar(int x) {\n  return x;\n}\n\nint Foo::bar(int x, int y) {\n  return x + y;\n}\n',
 "b.cc": '#include "a.h"\nvoid use1() { Foo f; f.bar(1); }\nvoid use2() { Foo f; f.bar(1, 2); }\n',
})
_h.build(d)
bad = False
for kind in ("change", "refactor"):
    rc, out = _h.dk("pack", "--project", d, kind, "Foo::bar")
    amb = "unambiguously" in out
    print(kind, "Foo::bar ->", out.strip().splitlines()[:6])
    if amb:
        bad = True
print("expected: a pack for Foo::bar (the documented Class::method form) with its callers use1/use2, "
      "or an ambiguity list whose entries differ (two identical `a.cc::Foo.bar` entries cannot be chosen between)")
sys.exit(1 if bad else 0)
