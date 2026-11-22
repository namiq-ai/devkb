"""#291: a pack for an overloaded C++ method resolves to the one node the overloads share, and says which caller reaches which overload by its
arguments; it never offers two identical choices. Fixture code is synthetic."""
from __future__ import annotations

import re

import cpp_support as S

FILES = {
    "a.h": "class A { public: int run(int x); int run(int x, int y); };\n",
    "a.cc": ('#include "a.h"\nint A::run(int x) { return x; }\nint A::run(int x, int y) { return x + y; }\n'
             "void one(A& a) { a.run(1); }\nvoid two(A& a) { a.run(1, 2); }\n"),
}


def _overload_rows(text):
    return [ln for ln in text.splitlines() if re.match(r"- `a\.cc:\d+` ", ln)]


def test_overloads_are_not_offered_as_identical_choices(tmp_path, monkeypatch):
    _a, p = S.api(tmp_path, FILES, monkeypatch)
    for text in (p.change("A::run"), p.refactor("A::run")):
        assert "cannot resolve" not in text and "Pass one as" not in text, text
        assert "## Overloads (2 share this node)" in text


def test_each_overload_lists_only_the_callers_whose_arguments_fit_it(tmp_path, monkeypatch):
    _a, p = S.api(tmp_path, FILES, monkeypatch)
    rows = _overload_rows(p.change("A::run"))
    assert len(rows) == 2, rows
    one_arg, two_args = rows
    assert "`one`" in one_arg and "`two`" not in one_arg, one_arg
    assert "`two`" in two_args and "`one`" not in two_args, two_args


def test_a_single_definition_has_no_overload_note(tmp_path, monkeypatch):
    _a, p = S.api(tmp_path, {"b.cc": "int solo(int x) { return x; }\nvoid use() { solo(1); }\n"}, monkeypatch)
    assert "## Overloads" not in p.change("solo")
