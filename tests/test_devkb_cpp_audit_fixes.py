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
