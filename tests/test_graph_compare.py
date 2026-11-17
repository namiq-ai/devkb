"""bench/graph_compare.py: a release is compared with the stored baseline; moved counts, a bigger graph or a slower build exit 1."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bench" / "graph_compare.py"


def _run(tmp_path, new_edit=None):
    repo = {"commit": "a" * 40, "commits_in_clone": 1, "files": 10, "build_secs": 10.0, "graph_mb": 5.0, "nodes": 1000, "edges": 2000,
            "node_types": {"Symbol": 800, "File": 200}, "edge_verbs": {"CALLS": 1000, "DEFINED_IN": 800, "STEP": 200}}
    base = {"label": "base", "code": "b" * 40, "repos": {"r": repo}}
    new = json.loads(json.dumps(base)); new["label"] = "new"
    if new_edit:
        new_edit(new["repos"]["r"])
    (tmp_path / "base.json").write_text(json.dumps(base)); (tmp_path / "new.json").write_text(json.dumps(new))
    return subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "base.json"), str(tmp_path / "new.json")], capture_output=True, text=True)


def test_identical_runs_pass(tmp_path):
    assert _run(tmp_path).returncode == 0


def test_step_edges_are_ignored(tmp_path):
    def edit(r):
        r["edge_verbs"]["STEP"] = 90; r["edges"] -= 110
    assert _run(tmp_path, edit).returncode == 0


def test_a_falling_call_count_fails(tmp_path):
    def edit(r):
        r["edge_verbs"]["CALLS"] = 800; r["edges"] -= 200
    out = _run(tmp_path, edit)
    assert out.returncode == 1 and "CALLS" in out.stdout


def test_a_slower_build_and_a_bigger_graph_fail(tmp_path):
    def edit(r):
        r["build_secs"] = 20.0; r["graph_mb"] = 9.0
    out = _run(tmp_path, edit)
    assert out.returncode == 1 and "build" in out.stdout and "size" in out.stdout


def test_a_different_commit_is_not_compared(tmp_path):
    def edit(r):
        r["commit"] = "c" * 40; r["nodes"] = 5
    out = _run(tmp_path, edit)
    assert out.returncode == 0 and "not comparable" in out.stdout
