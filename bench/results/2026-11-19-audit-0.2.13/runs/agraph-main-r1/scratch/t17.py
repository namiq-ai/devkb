import sys, time; sys.path.insert(0, "audit/scratch")
from h import *
def timed(files):
    d = mk(files); t = time.time(); build(d); return round(time.time() - t, 2)
shapes = {}
def big_class(n):
    return {"m.py": "class A:\n" + "".join(f"    def m{i}(self):\n        return self.m{(i+1)%n}() + self.m{(i+7)%n}()\n" for i in range(n))}
def many_same_name(n):
    return {f"f{i}.py": "def run():\n    return 1\n" for i in range(n)} | {"u.py": "".join(f"def u{i}():\n    return run()\n" for i in range(n))}
def many_globals(n):
    return {"m.py": "G = 0\n" + "".join(f"def g{i}():\n    global G\n    G = G + 1\n    return G\n" for i in range(n))}
def many_imports(n):
    f = {f"p{i}.py": f"X{i} = {i}\ndef fn{i}():\n    return X{i}\n" for i in range(n)}
    f["main.py"] = "".join(f"from p{i} import fn{i}, X{i}\n" for i in range(n)) + "def go():\n" + "".join(f"    fn{i}() + X{i}\n" for i in range(n))
    return f
def typed_one_file(n):
    return {"m.py": "class A:\n    def go(self):\n        return 1\n" + "".join(f"def f{i}():\n    a = A()\n    return a.go()\n" for i in range(n))}
def cpp_typed(n):
    return {"a.h": "class A { public: void go(); };\n", "a.cc": '#include "a.h"\nvoid A::go() {}\n' + "".join(f"void f{i}() {{ A a; a.go(); }}\n" for i in range(n))}
def cpp_macros(n):
    return {"a.h": "".join(f"#define M{i}(x) h{i}(x)\n" for i in range(n)), "a.cc": "".join(f"void h{i}(int){{}}\n" for i in range(n)) + "".join(f"void f{i}() {{ M{i}(1); }}\n" for i in range(n))}
def cpp_chain_macros(n):
    return {"a.h": "#define M0(x) leaf(x)\n" + "".join(f"#define M{i}(x) M{i-1}(x)\n" for i in range(1, n)), "a.cc": "void leaf(int){}\nvoid f() { M%d(1); }\n" % (n - 1)}
def cpp_testf(n):
    return {"t.cc": "class F { public: void go(); int x_; };\nvoid F::go(){}\n" + "".join(f"TEST_F(F, T{i}) {{ go(); }}\n" for i in range(n))}
def cpp_overloads(n):
    return {"a.h": "class A { public:\n" + "".join(f"  void go(int a{'' if i == 0 else ', int b' * i});\n" for i in range(1)) + "};\n", "a.cc": '#include "a.h"\n' + "".join(f"void A::go(int x) {{}}\n" for i in range(n)) + "void u(A& a){ a.go(1); }\n"}
for name, fn in [("big_class", big_class), ("many_same_name", many_same_name), ("many_globals", many_globals), ("many_imports", many_imports), ("typed_one_file", typed_one_file), ("cpp_typed", cpp_typed), ("cpp_macros", cpp_macros), ("cpp_chain_macros", cpp_chain_macros), ("cpp_testf", cpp_testf), ("cpp_overloads", cpp_overloads)]:
    ns = (25, 50, 100) if name in ("cpp_chain_macros",) else (300, 600, 1200)
    print(name, [(n, timed(fn(n))) for n in ns], flush=True)
