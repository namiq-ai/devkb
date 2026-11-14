"""ODSF-308: the lifecycle benchmark scores honestly, and review_pack answers a past commit correctly."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import process_api  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"bench_{name}", _REPO_ROOT / "devkb" / "bench" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run, report = _load("run"), _load("report")


def test_parse_takes_the_first_json_object_even_when_the_prose_contains_braces():
    text = 'I used {curly} words first.\n```json\n{"callers": ["a.py::f"], "owner": ["BE"]}\n```\nNote: {not json}.'
    assert run.parse(text) == {"callers": ["a.py::f"], "owner": ["BE"]}
    assert run.parse("no object here") == {} and run.parse("") == {}


def test_f1_compares_symbols_by_path_and_short_name_and_treats_two_empty_sets_as_a_match():
    assert run.f1(["pkg/a.py::Cls.method"], ["pkg/a.py::method"]) == 1.0
    assert run.f1(["a.py::x"], ["a.py::y"]) == 0.0
    assert run.f1([], []) == 1.0 and run.f1(["a.py::x"], []) == 0.0
    assert run.f1(["a.py::x", "a.py::z"], ["a.py::x", "a.py::y"]) == pytest.approx(0.5)


def test_scoring_by_task_kind():
    callers = {"kind": "callers", "truth": {"callers": ["a.py::f"], "test_files": ["t.py"], "owner": ["BE"], "forbidden_for": ["FE"]}}
    assert run.score(callers, json.dumps({"callers": ["a.py::f"], "test_files": ["t.py"], "owner": ["BE"], "forbidden_for": ["FE"]}))["score"] == 1.0
    assert run.score(callers, json.dumps({"callers": [], "test_files": [], "owner": ["BE"], "forbidden_for": ["FE"]}))["score"] == 0.5
    rules = {"kind": "set", "truth": {"failing_rules": ["R5"]}}
    assert run.score(rules, '{"failing_rules": ["R5"]}')["score"] == 1.0 and run.score(rules, '{"failing_rules": []}')["score"] == 0.0
    exact = {"kind": "exact", "truth": {"commits": 5, "epic": "E-1"}}
    assert run.score(exact, '{"commits": 5, "epic": "E-2"}')["score"] == 0.5


def _row(stage, arm, cost, graph_calls=0, valid=True, score=1.0, bytes_=1000):
    return {"stage": stage, "arm": arm, "valid": valid, "cost": cost, "turns": 5, "graph_calls": graph_calls, "result_bytes": bytes_,
            "fresh": 2000, "secs": 10, "score": score}


def test_the_report_excludes_invalid_runs_from_medians_and_states_adoption():
    rows = [_row("S1", "plain", 0.10), _row("S1", "plain", 0.30), _row("S1", "plain", 9.9, valid=False, score=0.0),
            _row("S1", "graph", 0.05, graph_calls=2), _row("S1", "graph", 0.15, graph_calls=0)]
    agg = report.aggregate(rows)
    assert agg["S1"]["plain"]["valid"] == 2 and agg["S1"]["plain"]["cost"] == pytest.approx(0.20)
    assert agg["S1"]["graph"]["adoption"] == 0.5
    table = report.render(agg)
    assert "| S1 | graph | 2/2 | 50% |" in table and "Sum of stage median costs" in table


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def test_review_pack_reads_a_past_commit_from_the_commit_not_from_the_moved_graph(tmp_path, monkeypatch):
    root = tmp_path
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("def other():\n    return 1\n\ndef save_record(x):\n    return x\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    (root / "pkg" / "a.py").write_text("def other():\n    return 1\n\ndef save_record(x):\n    return x + 1\n")
    _git(root, "commit", "-qam", "ODSF-9: change save_record")
    changed_commit = _git(root, "rev-parse", "HEAD")
    # A later commit shifts every line, so the graph (built at this commit) places the functions elsewhere.
    (root / "pkg" / "a.py").write_text("# a\n# b\n# c\n# d\n# e\n" + (root / "pkg" / "a.py").read_text())
    _git(root, "commit", "-qam", "later: add header")
    head = _git(root, "rev-parse", "HEAD")
    nodes = [
        {"uid": "s1", "type": "Symbol", "natural_key": "pkg/a.py::save_record", "source": "t", "properties": {"kind": "function", "line_start": 9, "line_end": 10}},
        {"uid": "s2", "type": "Symbol", "natural_key": "pkg/a.py::other", "source": "t", "properties": {"kind": "function", "line_start": 6, "line_end": 7}},
        {"uid": "s3", "type": "Symbol", "natural_key": "pkg/b.py::run", "source": "t", "properties": {"kind": "function", "line_start": 1, "line_end": 2}},
    ]
    edges = [{"from_uid": "s3", "to_uid": "s1", "verb": "CALLS", "properties": {}}]
    store = root / ".devkb"
    store.mkdir()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in nodes) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in edges) + "\n")
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-13T00:00:00+00:00", "git_head": head}))
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="ODSF", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    api = process_api.ProcessAPI("TST")
    r = api.call("review_pack", rev=changed_commit)
    assert r["changed_symbols"] == ["pkg/a.py::save_record"], "the diff's old line numbers must not be matched against the moved graph"
    assert r["callers_outside"] == ["pkg/b.py::run"] and r["drift"] == ["pkg/a.py"]
    # A diff at the graph's own commit still maps through the graph.
    at_head = api.call("review_pack", rev=head)
    assert "drift" not in at_head
