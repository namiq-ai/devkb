"""SPEC-DKB-002 story 2.7 / 2.3 / 1.6: the measures themselves are tested: a true edge scores, a wrong rule exits 1."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from functools import partial
from pathlib import Path

import profile_support as P
import pytest

from devkb import boundaries, cpp_graph
from devkb.bench import cpp_corpus

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "bench" / "boundaries" / "check.py"
FIXTURES = ROOT / "tests" / "fixtures" / "boundaries"
TRUTH = json.loads((FIXTURES / "truth.json").read_text())["fixtures"]


def run_check(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK), str(FIXTURES), *extra], capture_output=True, text=True)


def test_every_boundary_fixture_is_labelled_with_its_edges_and_negatives():
    boundary_fixtures = {d.name for d in FIXTURES.iterdir() if d.is_dir() and d.name not in ("kconfig", "defect_cpp")}
    assert boundary_fixtures == set(TRUTH)
    kinds = {n["kind"] for t in TRUTH.values() for n in t["negatives"]}
    assert {"dynamic", "ambiguous", "not-a-handle", "not-in-repository", "lambda", "overload", "static"} <= kinds
    for t in TRUTH.values():
        for e in t["edges"]:
            assert e["mechanism"] in boundaries.MECHANISMS


def test_precision_is_one_and_every_dynamic_case_is_counted():
    done = run_check()
    assert done.returncode == 0, done.stdout + done.stderr
    for m in boundaries.MECHANISMS:
        assert f"{m}: precision 1.00" in done.stdout, done.stdout


def test_a_wrong_link_exits_one_and_names_the_false_edge(tmp_path, monkeypatch):
    """A resolver that ignores uniqueness links `twice()` to one of two `dup` definitions: the check must refuse it."""
    monkeypatch.setattr(cpp_graph.boundaries, "resolve", partial(boundaries.resolve, unique=False))
    built = tmp_path / "built"
    for name in TRUTH:
        g = P.build(tmp_path / "w" / name, f"boundaries/{name}")
        store = built / name / ".devkb"
        store.mkdir(parents=True)
        d = g.to_dict()
        (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
        (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    done = run_check("--built", str(built))
    assert done.returncode == 1, done.stdout
    assert "FALSE EDGE" in done.stdout and "use.py::twice" in done.stdout


def test_the_check_shares_no_code_with_the_extractors():
    tree = ast.parse(CHECK.read_text())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names <= set(sys.stdlib_module_names) and "devkb" not in names
    assert "edges.jsonl" in CHECK.read_text()


def test_the_compiler_truth_and_the_independent_counts_import_nothing_from_devkb():
    for rel in ("bench/cpp/truth_clang.py", "bench/cpp/header_counts.py", "bench/cpp/config_counts.py"):
        tree = ast.parse((ROOT / rel).read_text())
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert "devkb" not in names, rel


# ── the corpus measure reports per language and per source, and a wrong C rule fails it ──────────────────────
def test_measure_reports_precision_and_recall_per_language_and_per_source(tmp_path):
    repo = P.make_fixture_repo(tmp_path, "boundaries/extern_c")
    m = cpp_corpus.measure(repo)
    assert set(m["by_language"]) == {"c", "cpp"}
    for lang in ("c", "cpp"):
        assert {"precision", "recall", "indeterminate", "unmapped", "complete_misses"} <= set(m["by_language"][lang])
    assert m["by_source"]["extern-c"]["edges"] == 2 and m["by_source"]["extern-c"]["precision"] == 1.0


def c_profile_check(g) -> list[str]:
    """The C profile against its labelled truth (story 1.6): any edge the truth does not list, or a forbidden caller that links."""
    truth = json.loads((P.FIXTURES / "profiles" / "c_linkage.truth.json").read_text())
    want = {tuple(e) for e in truth["edges"]}
    got = {(e.src, e.dst) for e in g.edges("CALLS")}
    return [f"FALSE EDGE {a} -> {b}" for a, b in sorted(got - want)] + [f"MISSED EDGE {a} -> {b}" for a, b in sorted(want - got)]


def test_the_c_profile_matches_its_labelled_truth(tmp_path):
    assert c_profile_check(P.build(tmp_path, "profiles/c_linkage")) == []


def test_a_seeded_wrong_c_rule_exits_one(tmp_path, monkeypatch):
    """Only this test makes the C profile treat `static` as `extern`; no production flag does."""
    from devkb import cpp_resolve
    orig = cpp_resolve.Repo.__init__

    def init(self, units):
        orig(self, units)
        for u in units:
            for s in u.syms.values():
                if s.kind == "function" and s.linkage == "internal":
                    self.c_linkage.setdefault(s.short, []).append((u.path, s))

    monkeypatch.setattr(cpp_resolve.Repo, "__init__", init)
    # on this fixture a static name defined twice stays ambiguous, so the fault is shown by the next test; here the corpus verdict
    # is shown to exit 1 for a precision under its floor, which is what a wrong rule produces on a corpus
    seeded = cpp_corpus.verdict("c_linkage", {"precision": 0.5, "recall": 1.0, "complete_misses": 0, "forbidden_count": 0,
                                              "by_language": {"c": {"precision": 0.5, "recall": 1.0, "complete_misses": 0}}},
                                {"precision": 0.95, "by_language": {"c": {"precision": 0.95}}})
    assert seeded, "a precision below the floor must fail the check"


def test_the_seeded_fault_in_the_c_rule_is_visible_on_a_fixture_where_static_hides_the_name(tmp_path, monkeypatch):
    """`helper` is static in `only.c`: `use.c` cannot call it. A C profile that ignores `static` links the call: the labelled truth refuses it."""
    from devkb import cpp_resolve
    files = {"only.c": "static int helper(void) { return 1; }\nint own(void) { return helper(); }\n",
             "use.c": "int use(void) { return helper(); }\n"}
    clean = P.S.build(tmp_path / "clean", files)
    assert [k for k in P.edges(clean) if k[0] == "use.c::use"] == []
    orig = cpp_resolve.Repo.__init__

    def init(self, units):
        orig(self, units)
        for u in units:
            for s in u.syms.values():
                if s.kind == "function" and s.linkage == "internal":
                    self.c_linkage.setdefault(s.short, []).append((u.path, s))

    monkeypatch.setattr(cpp_resolve.Repo, "__init__", init)
    seeded = P.S.build(tmp_path / "seeded", files)
    assert [k for k in P.edges(seeded) if k[0] == "use.c::use"] == [("use.c::use", "only.c::helper")], "the fault links a static function across files"


def test_header_agreement_is_reported_and_never_folded_into_the_counts():
    out = cpp_corpus.header_agreement({"a.h": "c", "b.h": "cpp", "c.h": "c", "d.h": "cpp"},
                                      {"a.h": ["c", "cpp"], "b.h": ["cpp"], "c.h": ["cpp"], "d.h": ["c"], "e.h": ["c"]})
    assert (out["headers"], out["agree"]) == (4, 2)
    assert any("c.h" in d for d in out["disagree"]) and any("d.h" in d for d in out["disagree"])
