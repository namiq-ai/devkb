from __future__ import annotations
# Hidden acceptance for #65 (from 08ed2ce).
"""The 0.2.5 -> 0.2.8 quality audit's C/C++ findings (#62..#66): each fixture fails on 4369145 and passes after its fix.

Fixture code is synthetic."""




import cpp_support as S


from devkb import cpp_symbols as cs


IFDEF = ("void a(void) {}\nvoid b(void) {}\nvoid c(void) {}\n"
         "#ifdef X\nvoid f(int x) {\n#else\nvoid f(int x, int y) {\n#endif\n  a();\n}\n"
         "void g(void) { b(); }\n"
         "#ifdef Y\nvoid h(int x) {\n  if (x) {\n#else\nvoid h(int x) {\n  if (!x) {\n#endif\n    c();\n  }\n}\n"
         "void k(void) { b(); }\n")


def test_template_pointer_and_reference_declarations_are_not_calls(tmp_path):
    src = ("int compute(int x) { return x; }\nint other(int x) { return x; }\nint third(int x) { return x; }\n"
           "void f() {\n  std::vector<int> compute(3);\n}\n")
    g = S.build(tmp_path, {"a.cpp": src})
    assert not [e for e in S.calls(g) if e[0] == "a.cpp::f"]


def test_comparisons_and_arithmetic_before_a_call_are_still_calls(tmp_path):
    src = ("int compute(int x) { return x; }\n"
           "int f(int a) {\n  int x = a * compute(3);\n  if (a > compute(1)) x++;\n  x = a & compute(2);\n  return x;\n}\n"
           "int g(int a) {\n  return a * compute(3);\n}\n")
    g = S.build(tmp_path, {"a.cpp": src})
    assert {("a.cpp::f", "a.cpp::compute"), ("a.cpp::g", "a.cpp::compute")} <= S.calls(g)
    r = cs.extract_file("a.cpp", src)
    cs.scan_bodies(r, {"compute"}, {"compute"})
    assert sorted(c.line for c in r.calls if c.name == "compute") == [3, 4, 5, 9]

