import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch"))
from h import *
d = mk({
    "a.h": "#define CALL(o) helper(); (o).put()\nclass Foo { public: void put(); };\n",
    "a.cc": '#include "a.h"\nvoid helper() {}\nvoid Foo::put() {}\nvoid use(Foo& f) { CALL(f); }\nvoid use2(Foo& f) { f.put(); }\n',
    "t.cc": '#include "a.h"\nTEST(A, B) { Foo f; f.put(); }\n',
})
build(d)
rc, out = dk("pack", "--project", d, "change", "Foo.put")
print(out[:1500])
bad = False
if "Run: ``" in out:
    print("DEFECT 1: pack prints an empty command `Run: ``` for C++ tests"); bad = True
if "no preprocessor expansion" in out:
    print("DEFECT 2: limits text says 'no preprocessor expansion' although repository macros are expanded (#118) and 'no overload resolution' although arity is used (#120)"); bad = True
sys.exit(1 if bad else 0)
