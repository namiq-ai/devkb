from __future__ import annotations
# Hidden acceptance for #63 (from 00ddd4e).
"""The 0.2.5 -> 0.2.8 quality audit's C/C++ findings (#62..#66): each fixture fails on 4369145 and passes after its fix.

Fixture code is synthetic."""




import cpp_support as S


from devkb import cpp_symbols as cs


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

