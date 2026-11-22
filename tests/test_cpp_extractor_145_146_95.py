"""#145, #146, #95: three wrong C++ call edges found in fmt's adjudicated sample (#117); each fixture fails on f1c1502 and passes after its fix.

Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S


def _from(g, caller):
    return {dst for src, dst in S.calls(g) if src == caller}


# #145: a name in a constructor's member-initialiser list is a member initialisation, not a call; calls in its arguments are still read
def test_a_member_initialiser_is_not_a_call_but_its_arguments_are(tmp_path):
    files = {"a.cpp": ("int m(int v) { return v; }\nint n(int v) { return v; }\nint f(int v) { return v; }\n"
                       "struct A {\n  A(int x) : m(x), n(f(x)) {}\n  int m; int n;\n};\n")}
    g = S.build(tmp_path, files)
    got = _from(g, "a.cpp::A.A")
    assert "a.cpp::f" in got, got
    assert "a.cpp::m" not in got and "a.cpp::n" not in got, got


def test_a_base_class_constructor_in_the_initialiser_list_stays_a_call(tmp_path):
    files = {"a.cpp": ("int make() { return 1; }\nvoid helper() {}\n"
                       "struct Base2 { Base2(int v) {} };\n"
                       "struct K : Base2 {\n  K() : Base2(make()), m_y(make()) { helper(); }\n  int m_y;\n};\n")}
    got = _from(S.build(tmp_path, files), "a.cpp::K.K")
    assert {"a.cpp::make", "a.cpp::helper", "a.cpp::Base2.Base2"} <= got, got


# #146: the second argument of EXPECT_CALL / ON_CALL names the mock's method; no edge to a same-named repository function
def test_a_gmock_expectation_names_a_method_it_does_not_call(tmp_path):
    files = {"a.cpp": ("int g(int v) { return v; }\nvoid allocate(int n) {}\n"
                       "struct Alloc { void allocate(int); };\n"
                       "void t(Alloc& mock) {\n  EXPECT_CALL(mock, allocate(g(1))).WillOnce(Return(0));\n  ON_CALL(mock, allocate(2));\n}\n")}
    got = _from(S.build(tmp_path, files), "a.cpp::t")
    assert "a.cpp::g" in got, got
    assert "a.cpp::allocate" not in got, got


# #95: a global function called from a same-named method is not linked to the method itself
def test_a_global_call_from_a_same_named_method_is_not_a_self_edge(tmp_path):
    files = {"a.cpp": ("int fileno(int fd) { return fd; }\n"
                       "class test {\n public:\n  int fileno(int fd) { return ::fileno(fd); }\n"
                       "  int close(int fd) { return FMT_POSIX(close(fd)); }\n};\nint close(int fd) { return fd; }\n")}
    g = S.build(tmp_path, files)
    assert ("a.cpp::test.fileno", "a.cpp::test.fileno") not in S.calls(g)
    assert ("a.cpp::test.close", "a.cpp::test.close") not in S.calls(g)
