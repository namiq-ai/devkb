"""DKB-006: the C/C++ corpus check refuses a wrong commit, measures against an independent truth, and fails on a seeded fault."""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

import cpp_support as S
from devkb import cpp_resolve
from devkb.bench import cpp_corpus, cpp_truth

ROOT = Path(__file__).resolve().parents[1]
FAULT_FILES = {
    "lib/shim.c": "void exit(int code) {}\n",
    "app/main.c": "int main(void) {\n  exit(1);\n  return 0;\n}\n",
}
CLEAN_FILES = {
    "core.c": "int core_init(void) { return 0; }\nint core_run(void) { return core_init(); }\n",
    "app.c": "int app_main(void) { return core_run(); }\n",
}


def test_corpus_pins_five_repositories_by_url_and_full_commit():
    corpus = cpp_corpus.load()
    assert [r["name"] for r in corpus["repos"]] == ["cJSON", "fmt", "leveldb", "autoas", "zephyr"]
    for r in corpus["repos"]:
        assert r["url"].startswith("https://") and re.fullmatch(r"[0-9a-f]{40}", r["commit"]), r
    assert {"precision"} <= set(corpus["floors"]["cJSON"]) and corpus["budgets"]["zephyr"] == 120 and corpus["budgets"]["cJSON"] == 5
    assert "reference_machine" in corpus


def test_check_refuses_a_checkout_at_a_different_commit(tmp_path):
    repo = S.make_repo(tmp_path / "cJSON", CLEAN_FILES)
    with pytest.raises(cpp_corpus.PinMismatch):
        cpp_corpus.verify_pin(repo, "0" * 40)
    pinned = {"name": "cJSON", "url": "unused", "commit": "f" * 40}
    with pytest.raises(cpp_corpus.PinMismatch):
        cpp_corpus.fetch(pinned, tmp_path)
    cpp_corpus.verify_pin(repo, cpp_corpus.head(repo))


def test_a_clean_fixture_passes_and_reports_precision_recall_and_indeterminates(tmp_path):
    repo = S.make_repo(tmp_path / "clean", CLEAN_FILES)
    m, why = cpp_corpus.check_path(repo, "clean", {"precision": 0.95, "recall": 0.9})
    assert not why, why
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["determinate_edges"] == 2 and m["indeterminate_edges"] == 0
    assert m["complete_packs"] >= 1 and m["complete_misses"] == 0


def test_seeded_fault_linking_exit_across_files_makes_the_check_fail(tmp_path, monkeypatch):
    repo = S.make_repo(tmp_path / "fault", FAULT_FILES)
    _m, why = cpp_corpus.check_path(repo, "fault", {"precision": 0.95})
    assert not why, "with the denylist the library name is not linked"
    monkeypatch.setattr(cpp_resolve, "C_LIBRARY", frozenset())     # the fault lives only in this test's process
    repo2 = S.make_repo(tmp_path / "fault2", FAULT_FILES)
    m, why = cpp_corpus.check_path(repo2, "fault2", {"precision": 0.95})
    assert m["forbidden_count"] == 1 and why, "the cross-file link to a C library name must fail the check"
    assert any("C library name" in w for w in why)


def test_floor_breach_and_a_complete_pack_that_misses_a_caller_both_fail():
    good = {"precision": 1.0, "recall": 1.0, "complete_misses": 0, "complete_miss_detail": [], "forbidden_count": 0, "forbidden_edges": []}
    assert cpp_corpus.verdict("x", good, {"precision": 0.95, "recall": 0.9}) == []
    assert cpp_corpus.verdict("x", {**good, "precision": 0.9}, {"precision": 0.95})
    assert cpp_corpus.verdict("x", {**good, "recall": 0.5}, {"precision": 0.95, "recall": 0.9})
    assert cpp_corpus.verdict("x", {**good, "complete_misses": 1}, {"precision": 0.95}), "the Complete floor is 1.0 and not tunable"


def test_complete_rule_catches_a_pack_that_says_complete_but_misses_a_true_caller(tmp_path, monkeypatch):
    repo = S.make_repo(tmp_path / "lie", CLEAN_FILES)
    from devkb import build_symbols
    g = build_symbols.extract(repo)
    # remove the proven edge core_run -> core_init while every coverage property still says Complete
    g._edges = {e for e in g._edges if not (e.verb == "CALLS" and e.dst.endswith("::core_init"))}
    m = cpp_corpus.measure(repo, graph=g)
    assert m["complete_misses"] >= 1 and cpp_corpus.verdict("lie", m, {"precision": 0.95})


def test_truth_module_imports_nothing_from_devkb():
    tree = ast.parse((ROOT / "devkb/bench/cpp_truth.py").read_text())
    for node in ast.walk(tree):
        mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        assert not any(m.split(".")[0] == "devkb" for m in mods), mods


def test_dependency_check_passes_on_this_tree_and_fails_on_a_changed_list(tmp_path):
    assert cpp_corpus.check_dependencies() == []
    (tmp_path / "devkb").mkdir()
    (tmp_path / "devkb/x.py").write_text("import requests\n")
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["pyyaml>=6", "requests"]\n')
    problems = cpp_corpus.check_dependencies(tmp_path, {})
    assert any("dependencies is" in p for p in problems) and any("imports requests" in p for p in problems)


def test_python_only_repository_builds_byte_identical_graph_with_the_cpp_pass_present(tmp_path):
    from devkb import build_symbols, cpp_graph
    root = S.make_repo(tmp_path, {"app/__init__.py": "", "app/a.py": "def f():\n    return g()\n\n\ndef g():\n    return 1\n"})
    with_pass = json.dumps(build_symbols.extract(root).to_dict(), sort_keys=True)
    original = cpp_graph.add_to_graph
    cpp_graph.add_to_graph = lambda *a, **k: None
    try:
        without = json.dumps(build_symbols.extract(root).to_dict(), sort_keys=True)
    finally:
        cpp_graph.add_to_graph = original
    assert with_pass == without
    assert not [n for n in build_symbols.extract(root).nodes() if n.source == "cpp-symbols"]


def test_this_repository_has_no_cpp_files_so_its_graph_has_no_cpp_rows():
    # test fixtures are C/C++ on purpose; the product itself has none
    tracked = subprocess.run(["git", "ls-files", "*.c", "*.cc", "*.cpp", "*.h", "*.hpp"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert not [f for f in tracked if not f.startswith("tests/fixtures/")]


def test_make_cpp_check_exists_and_is_not_a_gate_dependency():
    text = (ROOT / "Makefile").read_text()
    assert re.search(r"(?m)^cpp-check:", text) and "devkb.bench.cpp_corpus" in text
    for line in text.splitlines():
        if line.startswith(("gate-1:", "gate-2:")):
            assert "cpp-check" not in line
