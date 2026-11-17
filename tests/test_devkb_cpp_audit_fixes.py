"""The 0.2.5 -> 0.2.8 quality audit's C/C++ findings (#62..#66): each fixture fails on 4369145 and passes after its fix.

Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S

from devkb import cpp_symbols as cs


# #62: one identifier is never split into a fake type and a local name
def test_an_identifier_is_not_split_into_a_type_and_a_local(tmp_path):
    files = {"a.cpp": ("class Task { public: void run(); };\nclass Runner { public: void run(); };\n"
                       "void Task::run() {}\nvoid Runner::run() {}\n"
                       "void use(int);\n"
                       "class Owner {\n public:\n  Runner* s;\n  void go() {\n    use(Tasks);\n    s->run();\n  }\n};\n")}
    g = S.build(tmp_path, files)
    assert ("a.cpp::Owner.go", "a.cpp::Task.run") not in S.calls(g)
    r = cs.extract_file("b.cpp", "void f(Foo* p) { g(tmp); p->x(); }")
    loc = r.scanner.locals_of(r.defs[0])
    assert loc["p"] == {("Foo", "*")} and "tmp" not in loc, "`tmp` is not a `tm` named `p`"


def test_typed_locals_with_and_without_a_space_still_read(tmp_path):
    r = cs.extract_file("b.cpp", "void f() { Foo* a = 0; Foo *b = 0; Foo &c = x; Foo d; const Bar* e = 0; Foo*f = 0; }")
    loc = r.scanner.locals_of(r.defs[0])
    assert loc["a"] == {("Foo", "*")} and loc["b"] == {("Foo", "*")} and loc["c"] == {("Foo", "&")}
    assert loc["d"] == {("Foo", "")} and loc["e"] == {("Bar", "*")} and loc["f"] == {("Foo", "*")}


# #63: a brace-initialised member in a constructor's initialiser list is not the constructor's body
def test_a_brace_initialised_member_is_not_the_constructor_body(tmp_path):
    files = {"a.cpp": ("void helper() {}\nint make() { return 1; }\nstruct Base { Base(int); };\n"
                       "class K : public Base {\n public:\n  K() : Base{2}, m_x{1}, m_y(make()) {\n    helper();\n  }\n"
                       "  int m_x; int m_y;\n};\n")}
    g = S.build(tmp_path, files)
    syms = S.symbols(g)
    assert "a.cpp::K.m_y" not in syms and "a.cpp::K.m_x" not in syms
    k = syms["a.cpp::K.K"]
    assert (k.props["line_start"], k.props["line_end"]) == (6, 8)
    assert {d for s, d in S.calls(g) if s == "a.cpp::K.K"} == {"a.cpp::make", "a.cpp::helper"}


def test_out_of_class_constructor_with_brace_initialisers_and_class_bases_still_read(tmp_path):
    files = {"a.cpp": ("void helper() {}\nstruct A {};\nstruct B {};\nstruct C : A, B { C(); int x; };\n"
                       "C::C() : x{helper2()} { helper(); }\nint helper2() { return 0; }\nvoid after() { helper(); }\n")}
    g = S.build(tmp_path, files)
    syms = S.symbols(g)
    assert {"a.cpp::C", "a.cpp::C.C", "a.cpp::helper2", "a.cpp::after"} <= set(syms)
    assert {d for s, d in S.calls(g) if s == "a.cpp::C.C"} == {"a.cpp::helper", "a.cpp::helper2"}
    assert ("a.cpp::after", "a.cpp::helper") in S.calls(g)


# #64: a function whose `{` never closes (signature variants under #ifdef/#else) does not swallow the rest of the file
IFDEF = ("void a(void) {}\nvoid b(void) {}\nvoid c(void) {}\n"
         "#ifdef X\nvoid f(int x) {\n#else\nvoid f(int x, int y) {\n#endif\n  a();\n}\n"
         "void g(void) { b(); }\n"
         "#ifdef Y\nvoid h(int x) {\n  if (x) {\n#else\nvoid h(int x) {\n  if (!x) {\n#endif\n    c();\n  }\n}\n"
         "void k(void) { b(); }\n")


def test_unbalanced_ifdef_signatures_do_not_swallow_the_rest_of_the_file(tmp_path):
    g = S.build(tmp_path, {"a.c": IFDEF})
    syms, edges = S.symbols(g), S.calls(g)
    assert {"a.c::g", "a.c::k"} <= set(syms)
    assert ("a.c::g", "a.c::b") in edges and ("a.c::k", "a.c::b") in edges
    assert ("a.c::f", "a.c::b") not in edges and ("a.c::f", "a.c::c") not in edges
    assert syms["a.c::f"].props["line_end"] < 12
    assert not [e for e in edges if e[0] == "a.c::h" and e[1] != "a.c::c"], "h, when read at all, calls only c"


def test_a_function_with_block_openers_under_ifdef_else_keeps_its_body(tmp_path):
    src = ("void set(int i) {}\nvoid b(void) {}\n"
           "void init(void)\n{\n  int i = 0;\n#if defined(A)\n  for (; i < 4; i++) {\n#else\n  for (; i < 8; i++) {\n#endif\n"
           "    set(i);\n  }\n}\nvoid after(void) { b(); }\n")
    g = S.build(tmp_path, {"a.c": src})
    syms, edges = S.symbols(g), S.calls(g)
    assert (syms["a.c::init"].props["line_start"], syms["a.c::init"].props["line_end"]) == (3, 13)
    assert ("a.c::init", "a.c::set") in edges and ("a.c::after", "a.c::b") in edges
    assert ("a.c::init", "a.c::b") not in edges


def test_the_else_branch_of_if_0_is_still_read(tmp_path):
    src = "void b(void) {}\n#if 0\nvoid f(int x) {\n#else\nvoid f(int x, int y) {\n#endif\n  b();\n}\nvoid g(void) { b(); }\n"
    g = S.build(tmp_path, {"a.c": src})
    assert {("a.c::f", "a.c::b"), ("a.c::g", "a.c::b")} <= S.calls(g)


def test_unbalanced_brace_inside_a_class_does_not_hide_later_functions(tmp_path):
    src = ("void b() {}\nclass C {\n public:\n#ifdef X\n  void f() {\n#else\n  void f(int) {\n#endif\n  }\n};\n"
           "void g() { b(); }\n")
    g = S.build(tmp_path, {"a.cpp": src})
    assert any(k.endswith(".g") or k.endswith("::g") for k in S.symbols(g))
    assert not [e for e in S.calls(g) if e[1] == "a.cpp::b" and "f" in e[0].rsplit(".", 1)[-1]]


def test_a_function_defined_inside_an_else_branch_keeps_its_body(tmp_path):
    src = ("void out(int c) {}\nvoid b(void) {}\n#ifdef A\nvoid w(int n) { out(n); }\n#else\nvoid w(int n)\n{\n"
           "#if defined(BIG)\n  for (int i = n; i; --i) {\n#else\n  for (int i = 0; i < n; ++i) {\n#endif\n    out(i);\n  }\n}\n#endif\n"
           "void after(void) { b(); }\n")
    g = S.build(tmp_path, {"a.c": src})
    syms, edges = S.symbols(g), S.calls(g)
    assert syms["a.c::w"].props["line_end"] == 15
    assert ("a.c::w", "a.c::out") in edges and ("a.c::after", "a.c::b") in edges and ("a.c::w", "a.c::b") not in edges


# #65: a declaration whose type ends in `>`, `*` or `&` is not a call to a function of the declared name
def test_template_pointer_and_reference_declarations_are_not_calls(tmp_path):
    src = ("int compute(int x) { return x; }\nint other(int x) { return x; }\nint third(int x) { return x; }\n"
           "void f() {\n  std::vector<int> compute(3);\n  Foo *other(nullptr);\n  const ns::Bar<T>& third(x);\n}\n")
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


# #66: indirect-reference resolution is near-linear in a function table's size
def _table(n: int) -> str:
    src = "".join(f"static int f{i}(int x) {{ return x; }}\n" for i in range(n))
    return src + "void (*tab[])(void) = {\n" + "".join(f"  f{i},\n" for i in range(n)) + "};\n"


def test_indirect_refs_on_a_4000_entry_function_table_take_under_a_second():
    import time
    r = cs.extract_file("t.c", _table(4000))
    names = {f"f{i}" for i in range(4000)}
    cs.scan_bodies(r, names, names)
    t = time.perf_counter()
    out = cs.indirect_refs(r, names)
    assert time.perf_counter() - t < 1.0
    assert sorted(n for n, _l, _o in out) == sorted(names)


def test_indirect_refs_keep_their_owner_with_two_definitions_on_one_line():
    # owners are found by line, as before #66: on a line holding two bodies the first one owns every reference
    src = ("int a(int x) { return x; }\nint b(int x) { return x; }\n"
           "void p(void) { use(a); } void q(void) { use(b); }\n"
           "void r(void) {\n  int a = 1;\n  use(a);\n  use(b);\n}\n")
    r = cs.extract_file("t.c", src)
    names = {"a", "b"}
    cs.scan_bodies(r, names | {"use"}, names)
    by_idx = {d.index: d.qn for d in r.defs}
    got = sorted((n, line, by_idx.get(o)) for n, line, o in cs.indirect_refs(r, names))
    assert got == [("a", 3, "p"), ("b", 3, "p"), ("b", 7, "r")]
