"""Defects the two-way review of PR #404 found; each fixture fails on be870c4 and passes after its fix. Fixture code is synthetic."""
from __future__ import annotations

import re
import subprocess

import cpp_support as S


def _from(g, caller):
    return {dst for src, dst in S.calls(g) if src == caller}


def test_a_ternary_or_label_in_a_test_macro_body_is_not_an_initialiser_list(tmp_path):
    files = {"a.cc": ("int f(int) { return 1; }\nint g2(int) { return 2; }\nint h() { return 3; }\n"
                      "TEST(Suite, Name) {\n  int c = 1;\n  int x = c ? f(1) : g2(2);\n  h();\n}\n")}
    got = _from(S.build(tmp_path, files), "a.cc::Suite.Name")
    assert {"a.cc::f", "a.cc::g2", "a.cc::h"} <= got, got


def test_undef_then_define_is_a_macro_again(tmp_path):
    files = {"a.cpp": "#undef LOG\n#define LOG(x) emit(x)\nvoid emit(int x) {}\nvoid u() { LOG(1); }\n"}
    assert "a.cpp::emit" in _from(S.build(tmp_path, files), "a.cpp::u")


def test_define_undef_define_expands_and_use_between_undef_and_redefine_does_not(tmp_path):
    files = {"a.cpp": ("void bar(int) {}\nvoid foo(int) {}\n#define foo(x) bar(x)\nvoid a() { foo(1); }\n#undef foo\nvoid b() { foo(2); }\n"
                       "#define foo(x) bar(x)\nvoid c() { foo(3); }\n")}
    g = S.build(tmp_path, files)
    assert "a.cpp::bar" in _from(g, "a.cpp::a") and "a.cpp::bar" in _from(g, "a.cpp::c")
    assert "a.cpp::bar" not in _from(g, "a.cpp::b"), "between the #undef and the redefinition it is the function foo"


def test_recursion_through_a_common_macro_keeps_its_self_edge_but_an_adapter_macro_does_not(tmp_path):
    files = {"a.cc": ("class T {\n public:\n  int fib(int n);\n  int close(int fd);\n};\n"
                      "int T::fib(int n) { if (n < 2) return n; return MAX(fib(n - 1), 0); }\n"
                      "int close(int fd) { return fd; }\nint T::close(int fd) { return FMT_POSIX(close(fd)); }\n")}
    g = S.build(tmp_path, files)
    assert ("a.cc::T.fib", "a.cc::T.fib") in S.calls(g), "MAX is not an adapter: a recursive call stays one"
    assert ("a.cc::T.close", "a.cc::T.close") not in S.calls(g), "FMT_POSIX adapts the global call (#95)"


def _py(tmp_path, files):
    import json

    from devkb.cli import main
    for rel, text in files.items():
        (tmp_path / rel).write_text(text)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@e.x", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=tmp_path, check=True, capture_output=True)
    assert main(["build", "--project", str(tmp_path)]) == 0
    return {json.loads(line)["properties"].get("evidence_ref", "") for line in (tmp_path / ".devkb" / "edges.jsonl").read_text().splitlines()
            if json.loads(line).get("verb") == "CALLS"}


def test_a_tuple_helper_that_returns_inside_try_or_with_still_types_its_callers_receivers(tmp_path):
    refs = _py(tmp_path, {
        "m.py": "class A:\n    def go(self):\n        return 1\n\n\nclass B:\n    def go(self):\n        return 2\n",
        "h.py": ("from m import A, B\n\n\ndef guarded():\n    try:\n        a = A()\n        return a, 1\n    except ValueError:\n        raise\n\n\n"
                 "def used():\n    x, n = guarded()\n    x.go()\n"),
    })
    assert any(r.startswith("h.py::used calls go on a A") for r in refs), sorted(refs)


def test_a_mock_expression_with_nested_calls_keeps_reading_calls_after_an_inner_comma(tmp_path):
    files = {"a.cc": ("int g(int) { return 1; }\nint h(int) { return 2; }\nint foo() { return 3; }\n"
                      "void t() { EXPECT_CALL(mk(g(1), h(2)), foo()); }\n")}
    got = _from(S.build(tmp_path, files), "a.cc::t")
    assert {"a.cc::g", "a.cc::h"} <= got and "a.cc::foo" not in got, got


def test_a_multi_line_overload_declaration_is_split_by_its_parameter_count(tmp_path, monkeypatch):
    files = {"a.h": "class A {\n public:\n  int run(int x);\n  int run(int x,\n          int y);\n};\n",
             "a.cc": ("#include \"a.h\"\nint A::run(int x) { return x; }\nint A::run(int x,\n              int y) { return x + y; }\n"
                      "void one(A& a) { a.run(1); }\nvoid two(A& a) { a.run(1, 2); }\n")}
    _a, p = S.api(tmp_path, files, monkeypatch)
    rows = [ln for ln in p.change("A::run").splitlines() if re.match(r"- `a\.cc:\d+` ", ln)]
    assert len(rows) == 2 and "`one`" in rows[0] and "`two`" not in rows[0] and "`two`" in rows[1] and "`one`" not in rows[1], rows
