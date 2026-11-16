"""DKB-002: C and C++ definitions become Symbols with the line that proves them (ADR-DEVKB-008 §2)."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import cpp_support as S

FILES = {
    "src/util.c": ('#include <stdio.h>\n#define PUBLIC(t) t\nstatic int helper(int a) {\n    return a + 1;\n}\n'
                   'PUBLIC(int) util_add(int a, int b) {\n    return helper(a) + b;\n}\n'
                   'typedef struct node { int v; } node_t;\nenum mode { MODE_A, MODE_B };\n'),
    "src/table.h": ('#pragma once\nnamespace db {\nclass Table : public Base {\n public:\n  Table(int n) : n_(n) { Reset(); }\n'
                    '  ~Table();\n  bool operator==(const Table& o) const { return n_ == o.n_; }\n  void Add(int v);\n'
                    '  void Add(int v, int w);\n  void Reset() { n_ = 0; }\n  class Iter {\n   public:\n'
                    '    bool Next() { return false; }\n  };\n private:\n  int n_;\n};\n}  // namespace db\n'),
    "src/table.cc": ('#include "table.h"\nnamespace db {\nTable::~Table() {}\nvoid Table::Add(int v) { n_ += v; }\n'
                     'void Table::Add(int v, int w) { Add(v); Add(w); }\n}\n'),
    "src/color.hpp": 'enum class Color : int { Red, Green };\nstruct Point { int x; int y; };\nunion U { int a; float b; };\n',
    "third_party/dep.c": "int vendored(void) { return 0; }\n",
    "src/api.pb.h": "inline int generated() { return 1; }\n",
}

EXPECTED = {
    ("function", "helper", 3), ("function", "util_add", 6), ("class", "node", 9), ("enum", "mode", 10),
    ("class", "Table", 3), ("method", "Table.Table", 5), ("method", "Table.~Table", 3), ("method", "Table.operator==", 7),
    ("method", "Table.Add", 4), ("method", "Table.Reset", 10), ("class", "Table.Iter", 11), ("method", "Table.Iter.Next", 13),
    ("enum", "Color", 1), ("class", "Point", 2), ("class", "U", 3),
}


def test_fixture_yields_exactly_the_expected_kind_name_line(tmp_path):
    g = S.build(tmp_path, FILES)
    got = {(n.props["kind"], n.props["qualified_name"], n.props["line_start"]) for n in S.symbols(g).values()}
    assert got == EXPECTED
    assert all(k.split("::")[0] not in ("third_party/dep.c", "src/api.pb.h") for k in S.symbols(g)), "vendored/generated skipped"


def test_macro_wrapped_return_type_is_found_and_overloads_share_one_node(tmp_path):
    g = S.build(tmp_path, FILES)
    syms = S.symbols(g)
    assert "src/util.c::util_add" in syms
    add = syms["src/table.cc::Table.Add"]
    assert add.props["overload_count"] == 2 and add.props["overload_lines"] == [4, 5] and add.props["line_start"] == 4
    assert syms["src/util.c::helper"].props["is_public"] is False, "a C static function is not public"
    assert syms["src/table.h::Table.Table"].props["kind"] == "method"


def test_namespace_macro_form_is_not_a_function(tmp_path):
    g = S.build(tmp_path, {"a.h": "namespace std _GLIBCXX_VISIBILITY(default) {\n}\n"})
    assert not S.symbols(g)
    g = S.build(tmp_path / "x", {"a.h": "namespace std _GLIBCXX_VISIBILITY(default) {\ninline void real() {}\n}\n"})
    assert [n.props["qualified_name"] for n in S.symbols(g).values()] == ["real"]


def test_the_line_at_line_start_contains_the_short_name(tmp_path):
    g = S.build(tmp_path, FILES)
    for key, node in S.symbols(g).items():
        path, qn = key.split("::", 1)
        line = (tmp_path / path).read_text().splitlines()[node.props["line_start"] - 1]
        assert qn.rsplit(".", 1)[-1] in line, (key, line)


def test_two_namespaces_colliding_in_one_file_take_the_namespace_prefix(tmp_path):
    g = S.build(tmp_path, {"a.cc": "namespace a { void run() {} }\nnamespace b { void run() {} }\nvoid solo() {}\n"})
    assert sorted(n.props["qualified_name"] for n in S.symbols(g).values()) == ["a.run", "b.run", "solo"]


def test_declarations_and_forward_declarations_create_no_symbol(tmp_path):
    g = S.build(tmp_path, {"a.h": "class Fwd;\nint decl(int);\nstruct S2;\nextern int g;\n"})
    assert not S.symbols(g)


def test_devkb_build_end_to_end_records_cpp_rows_and_the_manifest_report(tmp_path, monkeypatch):
    from devkb import build as build_mod, build_symbols, test_discovery
    monkeypatch.delenv("DEVKB_DIR", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    root = S.make_repo(tmp_path / "widgets", {
        "src/calc.cc": "int add(int a, int b) { return a + b; }\n",
        "tests/calc_test.cc": '#include <gtest/gtest.h>\nint add(int, int);\nTEST(Calc, Adds) { add(1, 2); }\nTEST_CASE("mystery") { }\n',
        "src/huge.c": "int huge(void) { return 0; }\n/* " + "x" * (2 * 1024 * 1024) + " */\n",
    })
    build_symbols.build(str(root))
    graph, devkb_dir = build_mod.build(str(root))
    manifest = json.loads((devkb_dir / "manifest.json").read_text())
    assert manifest["cpp"]["skipped"] == ["src/huge.c"] and manifest["cpp"]["tests_skipped_ambiguous"] == 1
    assert {n.props["function"] for n in graph.nodes("TestCase")} == {"Calc.Adds"}
    assert ("tests/calc_test.cc::Calc.Adds", "src/calc.cc::add") in {(e.src, e.dst) for e in graph.edges("CALLS")}
    assert test_discovery.tests_in_file(root, "tests/calc_test.cc") == [("Calc.Adds", 3)]


def test_dependencies_unchanged_and_import_needs_only_stdlib_and_pyyaml():
    root = Path(__file__).resolve().parents[1]
    assert 'dependencies = ["pyyaml>=6"]' in (root / "pyproject.toml").read_text()
    probe = textwrap.dedent('''
        import sys, importlib.abc
        allowed = set(sys.stdlib_module_names) | {"yaml", "devkb", "_yaml"}
        class Guard(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name.split(".")[0] not in allowed and not name.startswith("_"):
                    raise ImportError("non-stdlib import: " + name)
        sys.meta_path.insert(0, Guard())
        import devkb.build_symbols, devkb.cpp_symbols, devkb.cpp_resolve, devkb.cpp_graph
    ''')
    proc = subprocess.run([sys.executable, "-c", probe], cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
