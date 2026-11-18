"""DKB-004 story 1: the C/C++ measurement keeps recursion, lists uncompilable files, excludes vendored code, and adjudicates precision.

Fixtures are synthetic. The compiler truth tests need libclang (in the venv) and g++ (for the system include path)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import cpp_support as S

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench" / "cpp"
sys.path.insert(0, str(BENCH))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BENCH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


common = _load("common")
quality = _load("quality")
adjudicate = _load("adjudicate")

needs_clang = pytest.mark.skipif(
    importlib.util.find_spec("clang") is None or shutil.which("g++") is None, reason="libclang (pip install libclang) and g++ are needed")

FILES = {
    "src/core.c": "int fact(int n) { if (n <= 1) return 1; return n * fact(n - 1); }\nint twice(int n) { return fact(n) + fact(n); }\n",
    "src/win.c": "#include <no_such_platform_header.h>\nint win_only(void) { return 1; }\nint win_user(void) { return win_only(); }\n",
    "third_party/unity/unity.c": "int unity_leaf(void) { return 0; }\nint unity_run(void) { return unity_leaf(); }\n",
}


def _truth(tmp_path, extra=()):
    repo = S.make_repo(tmp_path / "proj", FILES)
    out = tmp_path / "truth.json"
    p = subprocess.run([sys.executable, str(BENCH / "truth_clang.py"), str(repo), str(out), "--vendored", "third_party", *extra],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return repo, json.loads(out.read_text())


@needs_clang
def test_truth_keeps_recursive_edges_lists_uncompilable_files_and_excludes_vendored(tmp_path):
    _repo, t = _truth(tmp_path)
    names = {usr: d[3] for usr, d in t["defs"].items()}
    edges = {(names[a], names[b]) for a, b in t["edges"]}
    assert ("fact", "fact") in edges, "a recursive call stays in the truth"
    assert ("twice", "fact") in edges
    assert t["not_compiled"] == ["src/win.c"] and "no_such_platform_header.h" in t["not_compiled_why"]["src/win.c"]
    assert "win_only" not in names.values() and "win_user" not in names.values(), "an uncompilable unit contributes no truth"
    assert not any(d[0].startswith("third_party/") for d in t["defs"].values()), "vendored code is not truth"
    assert t["vendored"] == ["third_party"]


def test_vendored_paths_come_from_the_corpus_file_by_whole_path_components():
    assert common.vendored_prefixes("cJSON") == ["tests/unity"]
    assert common.vendored_prefixes("fmt") == ["test/gtest"]
    assert common.vendored_prefixes("leveldb") == ["third_party"]
    assert common.vendored_prefixes("tinyxml2") == [] and common.vendored_prefixes("unknown") == []
    pre = ["test/gtest"]
    assert common.is_vendored("test/gtest/gtest/gtest.h", pre) and common.is_vendored("./test/gtest/a.cc", pre)
    assert not common.is_vendored("test/gtest-extra.cc", pre), "a sibling that merely shares the prefix text is fmt's own"
    assert not common.is_vendored("test/format-test.cc", pre)


def test_wilson_interval():
    lo, hi = common.wilson(100, 100)
    assert hi == pytest.approx(1.0) and 0.963 < lo < 0.964
    lo, hi = common.wilson(93, 100)
    assert 0.86 < lo < 0.87 and 0.96 < hi < 0.97
    assert common.wilson(0, 0) == (0.0, 1.0)


# a hand-made devkb output and truth: a (caller) calls b (callee), b calls itself, c calls d, and d is vendored
def _out():
    sym = lambda uid, key, ls=1, le=3: {"uid": uid, "key": key, "kind": "function", "ls": ls, "le": le, "lang": "c"}
    return {"secs": 0.1, "syms": [sym("A", "a.c::a"), sym("B", "b.c::b"), sym("C", "c.c::c"), sym("D", "third_party/d.c::d"),
                                   sym("W", "win.c::w"), sym("X", "x.c::x")],
            "edges": [["A", "B", 0.6, "cpp-unique-free", "a.c::a calls b"], ["B", "B", 0.8, "cpp-same-file", "b.c::b calls b"],
                      ["C", "D", 0.6, "cpp-unique-free", ""], ["W", "B", 0.6, "cpp-unique-free", ""], ["A", "X", 0.6, "cpp-unique-free", ""],
                      ["A", "C", 0.6, "cpp-unique-free", ""]]}


def _truth_json(**extra):
    defs = {"ua": ["a.c", 1, 3, "a"], "ub": ["b.c", 1, 3, "b"], "uc": ["c.c", 1, 3, "c"], "ux": ["x.c", 1, 3, "x"]}
    return {"defs": defs, "edges": [["ua", "ub"], ["ub", "ub"]], **extra}


def test_quality_scores_a_recursive_edge_and_separates_not_measured_and_vendored_from_wrong():
    truth = _truth_json(not_compiled=["win.c"], vendored=["third_party"])
    edges, mapping, _ = quality.classify_edges(_out(), truth, "proj")
    by = {(e["from"], e["to"]): e["status"] for e in edges}
    assert by[("B", "B")] == "correct", "recursion is scored against a truth that keeps it"
    assert by[("C", "D")] == "vendored" and by[("W", "B")] == "not_measured"
    assert by[("A", "X")] == "wrong" and by[("A", "C")] == "wrong"
    res, _src = quality.score(_out(), truth, "proj")
    assert (res["edges_scored"], res["wrong_edges"]) == (4, 2) and res["edge_precision"] == 0.5
    assert res["edges_not_measured"] == 1 and res["edges_vendored_excluded"] == 1 and res["edges_unmapped"] == 0
    assert res["not_compiled_files"] == ["win.c"] and res["truth_recursive_edges"] == 1
    assert res["symbols_vendored_excluded"] == 1 and res["symbols_not_measured"] == 1
    assert res["edge_recall"] == 1.0


def test_quality_reads_vendored_prefixes_from_the_corpus_file_when_the_truth_has_none():
    truth = _truth_json()
    old, _ = quality.score(_out(), truth, "proj")
    assert old["edges_vendored_excluded"] == 0, "no list, nothing excluded"
    with_corpus, _ = quality.score({**_out(), "syms": [dict(s, key=s["key"].replace("third_party/", "tests/unity/")) for s in _out()["syms"]]},
                                   truth, "cJSON")
    assert with_corpus["edges_vendored_excluded"] == 1 and with_corpus["vendored_prefixes"] == ["tests/unity"]


@needs_clang
def test_adjudicated_sample_is_seeded_judged_by_hand_and_reported_with_an_interval(tmp_path):
    repo, _ = _truth(tmp_path)
    truth_path = tmp_path / "truth.json"
    a, b, c = tmp_path / "s1.jsonl", tmp_path / "s2.jsonl", tmp_path / "s3.jsonl"
    adjudicate.draw(ROOT, repo, truth_path, a, n=3, seed=5)
    adjudicate.draw(ROOT, repo, truth_path, b, n=3, seed=5)
    adjudicate.draw(ROOT, repo, truth_path, c, n=1, seed=6)
    assert a.read_text() == b.read_text(), "the same seed draws the same sample"
    meta, rows = adjudicate.load(a)
    assert meta["seed"] == 5 and meta["excluded"]["not_compiled"] == ["src/win.c"] and meta["excluded"]["vendored"] == ["third_party"]
    assert len(rows) == min(3, meta["frame"]) and all(r["by"] == "truth" for r in rows if r["status"] == "truth")
    with pytest.raises(SystemExit):
        adjudicate.draw(ROOT, repo, truth_path, a, n=3, seed=5)           # would overwrite the verdicts


def test_judge_refuses_a_truth_edge_and_report_refuses_a_pending_edge_then_gives_the_interval(tmp_path):
    path = tmp_path / "s.jsonl"
    rows = [{"id": i, "caller": f"a.c::f{i}", "callee": "a.c::g", "source": "cpp-same-file", "status": st, "caller_span": [1, 2], "callee_line": 1,
             "truth_same_name_from_caller": [], "verdict": "correct" if st == "truth" else None, "by": "truth" if st == "truth" else None, "note": ""}
            for i, st in enumerate(["truth"] * 8 + ["wrong", "unmapped"], 1)]
    adjudicate.save(path, {"repo": "r", "seed": 1, "n": 10, "frame": 50, "frame_by_status": {}}, rows)
    with pytest.raises(SystemExit):
        adjudicate.judge(path, ["1=wrong"])                                # confirmed by the compiler, not by hand
    with pytest.raises(SystemExit):
        adjudicate.judge(path, ["9=maybe"])
    with pytest.raises(SystemExit):
        adjudicate.summarize(path)                                          # two edges still pending
    adjudicate.judge(path, ["9=wrong:calls another g", "10=correct:static g in the same file"])
    s = adjudicate.summarize(path)
    assert (s["n"], s["truth_confirmed"], s["hand_judged"], s["hand_correct"], s["hand_wrong"]) == (10, 8, 2, 1, 1)
    assert s["precision"] == 0.9 and 0.57 < s["low"] < 0.6 and 0.98 < s["high"] < 0.99
    assert s["by_source"]["cpp-same-file"] == {"n": 10, "correct": 9}


def test_the_committed_samples_are_complete_and_back_the_numbers_in_the_report():
    samples = ROOT / "docs" / "specs" / "cpp-samples"
    doc = (ROOT / "docs" / "specs" / "cpp-precision-sample.md").read_text()
    names = sorted(p.stem for p in samples.glob("*.jsonl"))
    assert names == ["cJSON", "fmt", "leveldb", "tinyxml2"]                 # three repositories of the corpus plus a third C++ one
    for name in names:
        s = adjudicate.summarize(samples / f"{name}.jsonl")                 # raises if an edge has no verdict
        assert s["n"] >= 100 and s["seed"] == 117
        assert f"{s['precision']:.3f}** ({s['correct']}/{s['n']}) | {s['low']:.3f} to {s['high']:.3f}" in doc, name
