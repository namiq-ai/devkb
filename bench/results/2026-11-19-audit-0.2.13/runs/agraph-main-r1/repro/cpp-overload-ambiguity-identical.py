import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch"))
from h import *
d = mk({
    "a.h": "class Foo { public: int get(int x); int get(int x, int y); };\n",
    "a.cc": '#include "a.h"\nint Foo::get(int x) { return x; }\nint Foo::get(int x, int y) { return x + y; }\n'
            "void use(Foo& f) { f.get(1); }\nvoid use2(Foo& f) { f.get(1, 2); }\n",
    "t.cc": "TEST(A, B) { int x = 1; }\n",
})
build(d)
rc, out = dk("pack", "--project", d, "change", "Foo::get")
print(out[:500])
items = re.findall(r"^- `(.+)`$", out, re.M)
bad = len(items) != len(set(items))
rc2, out2 = dk("pack", "--project", d, "change", "a.cc::Foo.get")
bad2 = "Run: ``" in out2
print("actual: the ambiguity list names the same `path::name` twice; the pack tells the agent to pass one as path::name, which cannot choose" if bad else "ok")
print("expected: entries are distinguishable (e.g. with the line, `a.cc:2::Foo.get`) and accepted back by pack")
sys.exit(1 if bad else 0)
