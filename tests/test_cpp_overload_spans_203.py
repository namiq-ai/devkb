"""#203: `symbol` and `outline` give each C++ overload its own range, and `--source` prints each body on its own.

Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S

from devkb import read_tools

SRC = ("#include <cstdio>\n"            # 1
       "\n"                              # 2
       "struct Box { int w; };\n"        # 3
       "\n"                              # 4
       "int helper(int x) { return x; }\n"   # 5
       "\n"                              # 6
       "\n"                              # 7
       "int area(int w) {\n"             # 8
       "  return w * w;\n"               # 9
       "}\n"                             # 10
       "\n"                              # 11
       "int area(int w, int h) {\n"      # 12
       "  return w * h + 7;\n"           # 13
       "}\n")                            # 14


def test_symbol_gives_each_overload_its_own_range_and_body(tmp_path, monkeypatch):
    a, _ = S.api(tmp_path, {"src/a.cpp": SRC}, monkeypatch)
    r = a.call("symbol", query="area", source=True)
    assert [(m["ls"], m["le"]) for m in r["matches"]] == [(8, 10), (12, 14)]
    first, second = (m["source"]["lines"] for m in r["matches"])
    assert any("w * w" in x for x in first) and not any("w * h" in x for x in first)
    assert any("w * h" in x for x in second) and not any("w * w" in x for x in second)
    text = read_tools.render_symbol(r)
    assert "L8-10" in text and "L12-14" in text and "L8-14" not in text


def test_outline_lists_each_overload_with_its_own_range(tmp_path, monkeypatch):
    a, _ = S.api(tmp_path, {"src/a.cpp": SRC}, monkeypatch)
    text = read_tools.render_outline(a.call("outline", path="src/a.cpp"))
    assert "function area  L8-10" in text and "function area  L12-14" in text and "L8-14" not in text


def test_a_single_definition_is_unchanged(tmp_path, monkeypatch):
    a, _ = S.api(tmp_path, {"src/a.cpp": SRC}, monkeypatch)
    r = a.call("symbol", query="helper")
    assert [(m["ls"], m["le"]) for m in r["matches"]] == [(5, 5)] and r["n"] == 1
