"""bench/cpp/quality.py maps a graph node, which stands for every overload of a name, to every compiler definition of those overloads (#119, #406):
an edge to `Slice` is correct when the truth has an edge to any `Slice` constructor. The older convention (the first overload only) stays behind
QUALITY_OVERLOAD=0 so both numbers can be reported."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "cpp"))


def _score(monkeypatch, aware):
    q = importlib.import_module("quality")
    monkeypatch.setattr(q, "OVERLOAD_AWARE", aware)
    truth = {"defs": {"c:caller": ["a.cc", 1, 9, "f"], "c:ctor_a": ["s.h", 3, 3, "ns.S.S"], "c:ctor_b": ["s.h", 4, 4, "ns.S.S"]},
             "edges": [["c:caller", "c:ctor_b"]], "not_compiled": [], "vendored": []}
    out = {"syms": [{"uid": 1, "key": "a.cc::f", "kind": "function", "ls": 1, "le": 9, "lang": "cpp", "spans": []},
                    {"uid": 2, "key": "s.h::S.S", "kind": "method", "ls": 3, "le": 3, "lang": "cpp", "spans": [[3, 3], [4, 4]]}],
           "edges": [[1, 2, 1.0, "cpp-constructor", "a.cc:5: f constructs S"]], "secs": 0.0}
    return q.score(out, truth, "r")[0]


def test_an_edge_to_the_merged_node_is_correct_when_the_truth_picked_another_overload(monkeypatch):
    aware = _score(monkeypatch, True)
    assert aware["correct_by_source"] == {"cpp-constructor": 1} and aware["wrong_edges"] == 0 and aware["edge_recall"] == 1.0, aware


def test_the_older_convention_scores_the_same_edge_wrong(monkeypatch):
    old = _score(monkeypatch, False)
    assert old["wrong_edges"] == 1 and old["edge_recall"] == 0.0, old
