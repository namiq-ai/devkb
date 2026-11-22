"""#292: a C/C++ pack's notes are true: its limits say what 0.2.15 resolves, and a pack that lists a C++ test never prints an empty `Run:`."""
from __future__ import annotations

import cpp_support as S

from devkb.cpp_symbols import CXX_LIMITS_TEXT

FILES = {
    "src/box.cc": "class Box { public: int size() const; };\nint Box::size() const { return 1; }\nint peek(Box* b) { return b->size(); }\n",
    "test/box_test.cc": "int peek(Box* b);\nTEST(BoxTest, Size) { Box b; peek(&b); }\n",
}


def test_the_limits_no_longer_say_there_is_no_macro_expansion_or_overload_resolution():
    assert "no preprocessor expansion" not in CXX_LIMITS_TEXT and "no overload resolution" not in CXX_LIMITS_TEXT
    assert "repository macro's calls are expanded" in CXX_LIMITS_TEXT and "argument count" in CXX_LIMITS_TEXT


def test_a_pack_that_lists_a_cpp_test_has_no_empty_run_command(tmp_path, monkeypatch):
    _a, p = S.api(tmp_path, FILES, monkeypatch)
    for text in (p.file("src/box.cc"), p.change("peek")):          # the packs that print a `Run:` line; `refactor` prints none
        assert "test/box_test.cc" in text and "Run: ``" not in text, text
        assert "Run: no command is known for these test files" in text
