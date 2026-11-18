"""#114 `uses` labels C++ hits by the definition that holds them and lists calls first; #115 each same-named definition keeps
its own range; #116 the Incomplete pack's file hint names the definition's own file.

Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S

from devkb import read_tools

TEMPLATES = (
    "template <typename T> int impl(int x);\n"                       # 1
    "int count(long n) { return 1; }\n"                              # 2
    "template <typename T> int count(T n) {\n  return 2;\n}\n"       # 3-5
    "template <typename T> int impl(int x);\n"                       # 6
    "extern template int impl<char>(int);\n"                         # 7
    "int wrap(int x) {\n  return impl<int>(x);\n}\n"                 # 8-10
    "int wrap2(int x) { return impl<char>(x); }\n"                   # 11
)


def test_uses_labels_each_hit_by_its_own_definition_and_lists_calls_first(tmp_path, monkeypatch):
    a, _ = S.api(tmp_path, {"t.cc": TEMPLATES}, monkeypatch)
    r = a.call("uses", name="impl")
    hits = {h["line"]: h for f in r["files"] for h in f["hits"]}
    assert hits[9]["in"] == "wrap" and hits[11]["in"] == "wrap2"
    for ln in (1, 6, 7):
        if ln in hits:
            assert hits[ln]["in"] is None, f"line {ln} is a top-level declaration"
    order = [h["line"] for f in r["files"] for h in f["hits"]]
    assert order[:2] == [9, 11], order            # calls first; a cut would drop declarations


def test_uses_lists_each_same_named_definition_with_its_own_range(tmp_path, monkeypatch):
    src = ("template <typename T> struct Acc {\n  static int delta(int x) { return x; }\n};\n"
           "int between() { return 0; }\n"
           "template <> struct Acc<double> {\n  static int delta(int x) {\n    return x + 1;\n  }\n};\n")
    a, _ = S.api(tmp_path, {"t.cc": src}, monkeypatch)
    r = a.call("uses", name="delta")
    assert [(d["ls"], d["le"]) for d in r["definitions"]] == [(2, 2), (6, 8)]
    assert read_tools.render_uses(r).count("defined:") == 2


def test_incomplete_hint_includes_the_definitions_own_file(tmp_path, monkeypatch):
    files = {"k.cc": "class Box {\n public:\n  void Add(int x) {}\n};\nvoid drive(Unknown* u) { u->Add(1); }\n",
             "m.cc": "void other(Mystery* p) { p->Add(2); }\n"}
    a, p = S.api(tmp_path, files, monkeypatch)
    text = p.change("Box.Add")
    assert "Search only these files" in text and "`k.cc`" in text, text
