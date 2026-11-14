"""ODSF-316 (ADDENDUM-1): the ablation switch removes exactly the coverage field, and the process-task truth reads git."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "devkb" / "bench"))

import process_tasks  # noqa: E402
import workflow_run  # noqa: E402


def _git(root, *a):
    return subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *a], cwd=root, check=True,
                          capture_output=True, text=True).stdout


def test_changed_functions_are_those_whose_body_a_commit_touched(tmp_path):
    (tmp_path / "app.py").write_text("def a():\n    return 1\n\n\ndef b():\n    return 2\n\n\ndef c():\n    return 3\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "start")
    (tmp_path / "app.py").write_text("def a():\n    return 1\n\n\ndef b():\n    return 20\n\n\ndef c():\n    return 3\n")
    _git(tmp_path, "commit", "-qam", "PRJ-7: change b")
    head = _git(tmp_path, "rev-parse", "HEAD").strip()
    assert process_tasks.changed_functions(tmp_path, head) == {("app.py", "b")}
    assert process_tasks.commits_for(tmp_path, "PRJ-7") == [head] and process_tasks.commits_for(tmp_path, "PRJ-70") == []
    assert process_tasks.trace("| Epic | PRJ-1 |\n| Specification | SPEC-PRJ-002 |\n") == {"epic": "PRJ-1", "spec": "SPEC-PRJ-002"}


def test_process_answers_are_scored_against_their_truth():
    tc = {"kind": "ticket_code", "truth": {"functions": ["a.py::b"], "test_files": ["tests/test_a.py"]}}
    assert workflow_run.score(tc, json.dumps({"functions": ["a.py::b"], "test_files": ["tests/test_a.py"]}))["score"] == 1.0
    tr = {"kind": "commit_trace", "truth": {"ticket": "PRJ-7", "epic": "PRJ-1", "spec": "SPEC-PRJ-002"}}
    assert workflow_run.score(tr, json.dumps({"ticket": "prj-7", "epic": "PRJ-1", "spec": "none"}))["score"] == 0.667


def test_the_ablation_switch_removes_coverage_and_nothing_else(monkeypatch, tmp_path):
    from devkb import process_api
    api = process_api.ProcessAPI.__new__(process_api.ProcessAPI)
    api.idx = type("I", (), {"built_at": "", "git_head": ""})()
    api.stale = type("S", (), {"check": lambda self: (False, "", 0)})()
    api.tel = type("T", (), {"log": lambda self, *a, **k: None})()
    api.fake = lambda: {"direct": ["x"], "coverage": {"complete": False}}
    monkeypatch.setenv("DEVKB_NO_COVERAGE", "1")
    r = process_api.ProcessAPI.call(api, "fake")
    assert "coverage" not in r and r["direct"] == ["x"]
    monkeypatch.delenv("DEVKB_NO_COVERAGE")
    assert "coverage" in process_api.ProcessAPI.call(api, "fake")
