"""DKB-007: the README row and the pack text state what C and C++ support cannot see, and each limit is demonstrated."""
from __future__ import annotations

import re
from pathlib import Path

import cpp_support as S
from devkb.cpp_symbols import CXX_LIMITS_TEXT

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()
# the three limits the README row names, each with the phrase that carries it
LIMITS = {"preprocessor": "no preprocessor expansion", "overload": "no overload resolution", "type inference": "no type inference"}

CPP = {
    "src/box.cc": "class Box { public: int size() const; };\nint Box::size() const { return 1; }\nint peek(Box* b) { return b->size(); }\n",
}
PY = {"app/__init__.py": "", "app/mod.py": "def helper():\n    return 1\n\n\ndef caller():\n    return helper()\n"}


def _row() -> str:
    rows = [ln for ln in README.splitlines() if ln.startswith("| C, C++")]
    assert len(rows) == 1, "C and C++ have their own README row"
    return rows[0]


def test_readme_row_is_partial_and_names_all_three_limits():
    row = _row()
    assert "Partial" in row and "Not yet" not in row
    for limit in LIMITS.values():
        assert limit in row, limit
    for limit in LIMITS.values():
        assert limit in CXX_LIMITS_TEXT, "the pack statement and the README name the same limits"


def test_only_the_cpp_pack_carries_the_limit_statement(tmp_path, monkeypatch):
    _a, cpp = S.api(tmp_path / "cpp", CPP, monkeypatch)
    text = cpp.refactor("Box.size", path="src/box.cc")
    assert CXX_LIMITS_TEXT in text
    assert text.index("## Coverage") < text.index(CXX_LIMITS_TEXT), "printed after the coverage line"
    assert "Complete." in text, "Complete or not, the limits follow"
    _b, py = S.api(tmp_path / "py", PY, monkeypatch)
    ptext = py.refactor("helper", path="app/mod.py")
    assert "C/C++ limits" not in ptext and "preprocessor" not in ptext
    assert "Complete." in ptext


def test_file_pack_of_a_cpp_file_carries_the_limit_statement_too(tmp_path, monkeypatch):
    _a, cpp = S.api(tmp_path, CPP, monkeypatch)
    assert CXX_LIMITS_TEXT in cpp.file("src/box.cc")


def test_limit_preprocessor_a_macro_generated_definition_is_not_seen(tmp_path):
    files = {"gen.c": "#define DEFINE_GETTER(n) int get_##n(void) { return 1; }\nDEFINE_GETTER(width)\nint plain(void) { return 0; }\n"}
    names = {n.props["qualified_name"] for n in S.symbols(S.build(tmp_path, files)).values()}
    assert names == {"plain"}, "get_width exists only after macro expansion, which devkb does not do"


def test_limit_overload_resolution_callers_of_every_overload_land_on_one_node(tmp_path):
    files = {"o.cc": ("class P { public: void put(int a); void put(const char *s); };\nvoid P::put(int a) {}\nvoid P::put(const char *s) {}\n"
                      "void use(P* p) { p->put(1); p->put(\"192.0.2.1\"); }\n")}
    g = S.build(tmp_path, files)
    node = S.symbols(g)["o.cc::P.put"]
    assert node.props["overload_count"] == 2
    assert S.calls(g) == {("o.cc::use", "o.cc::P.put")}, "both calls reach the single node: the graph does not pick an overload"


def test_limit_type_inference_a_call_through_auto_is_unresolved_not_guessed(tmp_path):
    files = {"t.cc": "class W { public: void run(); };\nvoid W::run() {}\nW* make();\nvoid go() { auto w = make(); w->run(); }\n"}
    g = S.build(tmp_path, files)
    assert not S.calls(g)
    assert S.symbols(g)["t.cc::W.run"].props["unresolved_calls"] == 1


def test_every_limit_named_in_the_readme_has_a_test_in_this_file():
    names = {n for n in globals() if n.startswith("test_limit_")}
    assert {"test_limit_preprocessor_a_macro_generated_definition_is_not_seen",
            "test_limit_overload_resolution_callers_of_every_overload_land_on_one_node",
            "test_limit_type_inference_a_call_through_auto_is_unresolved_not_guessed"} == names
    assert len(LIMITS) == len(names) and all(re.search(k, " ".join(names).replace("_", " ")) for k in LIMITS)
