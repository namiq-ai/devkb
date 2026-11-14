"""ODSF-306: the process API answers development questions from a compact graph.

The graph is hand-built JSONL in a throwaway git repo, so every expected
answer is known in advance and none of it depends on a real build.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import process_api, service  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _node(uid, typ, key, **props):
    return {"uid": uid, "type": typ, "natural_key": key, "source": "t", "properties": props}


def _edge(a, verb, b, **props):
    return {"from_uid": a, "to_uid": b, "verb": verb, "properties": props}


@pytest.fixture
def api(tmp_path, monkeypatch):
    root = tmp_path
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("def save_record(x):\n    return x\n\ndef other():\n    return 1\n")
    (root / "pkg" / "b.py").write_text("from pkg import a\n\ndef run():\n    a.save_record(1)\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("from pkg import a\n\ndef test_save():\n    a.save_record(1)\n")
    (root / "docs").mkdir()
    (root / "docs" / "readiness.md").write_text("# Readiness gate rules\n\n## Stories\n")
    (root / "docs" / "other.md").write_text("# Unrelated notes\n")
    (root / "sdp" / "process" / "roles").mkdir(parents=True)
    (root / "sdp" / "process" / "roles" / "be.md").write_text("### OWN:\n```\npkg/\n```\n### DO NOT TOUCH:\n```\nweb/\n```\n")
    (root / "sdp" / "process" / "roles" / "fe.md").write_text("### OWN:\n```\nweb/\n```\n### DO NOT TOUCH:\n```\npkg/\n```\n")
    (root / "pms.config.json").write_text(json.dumps({
        "role_profiles": {"BE": "be.md", "FE": "fe.md"},
        "component_to_role": {"PMS": "BE"},
        "subsystems": [{"key": "pkg", "path": "pkg"}]}))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "ODSF-9: first")
    first = _git(root, "rev-parse", "HEAD")
    (root / "pkg" / "a.py").write_text("def save_record(x):\n    return x + 1\n\ndef other():\n    return 1\n")
    _git(root, "commit", "-qam", "ODSF-9: change save_record")
    head = _git(root, "rev-parse", "HEAD")

    nodes = [
        _node("s1", "Symbol", "pkg/a.py::save_record", kind="function", line_start=1, line_end=2),
        _node("s2", "Symbol", "pkg/a.py::other", kind="function", line_start=4, line_end=5),
        _node("s3", "Symbol", "pkg/b.py::run", kind="function", line_start=3, line_end=4),
        _node("s4", "Symbol", "tests/test_a.py::test_save", kind="function", line_start=3, line_end=4),
        _node("s5", "Symbol", "pkg/a.py::dup", kind="function", line_start=7, line_end=8),
        _node("s6", "Symbol", "pkg/b.py::dup", kind="function", line_start=7, line_end=8),
        _node("e1", "Endpoint", "POST /save", method="POST", path="/save", owner_symbol="pkg/b.py::run"),
        _node("t1", "Ticket", "ODSF-9", title="Save records", ticket_type="STORY", status="OPEN", component="PMS", assignee="BE",
              priority="P2", issue_path="issues/ODSF-9.md"),
        _node("t2", "Ticket", "ODSF-8", title="Epic", ticket_type="EPIC", status="OPEN"),
        _node("t3", "Ticket", "ODSF-7", title="Similar", ticket_type="TASK", status="DONE"),
        _node("sp1", "Spec", "docs/readiness.md", title="Readiness gate rules", doc_type="specification", status="accepted", spec_id="SPEC-X-1"),
        _node("sp2", "Spec", "docs/other.md", title="Unrelated notes", doc_type="design", status="draft"),
        _node("f1", "File", "pkg/a.py"),
        _node("c1", "Commit", "c" * 40, short_hash="cccccccccc", subject="ODSF-9: x", date="2026-11-01"),
        _node("tc1", "TestCase", "tests/test_a.py:3", file="tests/test_a.py", function="test_save", line=3),
        _node("w1", "Warning", "w1", rule="DEV-06", severity="HIGH", detail="x"),
    ]
    edges = [
        _edge("s3", "CALLS", "s1"), _edge("s4", "CALLS", "s1"), _edge("s4", "CALLS", "s3"),
        _edge("s1", "TESTED_BY", "tc1"), _edge("t1", "CHILD_OF", "t2"), _edge("sp1", "DOCUMENTS", "t1"),
        _edge("t1", "IMPLEMENTS", "sp1"), _edge("t1", "SIMILAR_TO", "t3", weighted_score=0.4),
        _edge("c1", "REFERENCES", "t1"), _edge("c1", "TOUCHES", "f1"), _edge("f1", "FLAGGED_BY", "w1"),
    ]
    store = root / ".devkb"
    store.mkdir()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in nodes) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in edges) + "\n")
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-13T00:00:00+00:00", "git_head": first}))
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="ODSF", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    api = process_api.ProcessAPI("TST")
    api.head = head
    return api


def test_callers_split_direct_from_indirect_and_report_the_ambiguous_name(api):
    r = api.call("callers", symbol="save_record", depth=2)
    assert set(r["direct"]) == {"pkg/b.py::run", "tests/test_a.py::test_save"}
    assert r["direct"][0] == "pkg/b.py::run", "non-test callers are listed before tests"
    amb = api.call("callers", symbol="dup")
    assert "error" in amb and set(amb["matches"]) == {"pkg/a.py::dup", "pkg/b.py::dup"}


def test_tests_for_a_file_lists_the_linked_tests_and_a_runnable_line(api):
    r = api.call("tests_for", ref="pkg/a.py")
    assert r["files"] == [{"f": "tests/test_a.py", "t": ["test_save"]}]
    assert r["run"] == "python3 -m pytest tests/test_a.py -q"


def test_tests_to_run_includes_a_changed_test_file_and_admits_an_unknown_file(api):
    assert api.call("tests_to_run", files=["tests/test_a.py"])["tests"] == ["tests/test_a.py"]
    r = api.call("tests_to_run", files=["nothing/known.py"])
    assert r["tests"] == [] and "full suite" in r["note"] and r["known_to_graph"] == 0


def test_impact_reaches_endpoints_through_callers_and_names_the_owner(api):
    r = api.call("impact", files=["pkg/a.py"])
    assert r["affected_files"] and {"f": "pkg/b.py", "n": 1} in r["affected_files"]
    assert "POST /save" in r["endpoints"]
    assert r["tests"] == ["tests/test_a.py"] and "BE" in r["owners"]


def test_owner_returns_the_owning_role_and_the_roles_fenced_out(api):
    r = api.call("owner", path="pkg/x.py")
    assert r["owner"] == ["BE"] and r["forbidden_for"] == ["FE"] and r["subsystem"] == "pkg"
    assert "no role owns" in api.call("owner", path="elsewhere/y.py")["note"]


def test_find_docs_ranks_by_title_and_headings_and_filters_by_kind(api):
    r = api.call("find_docs", topic="readiness gate")
    assert r["docs"][0]["p"] == "docs/readiness.md" and len(r["docs"]) == 1
    assert api.call("find_docs", topic="readiness", kinds=["design"])["docs"] == []
    assert api.call("find_docs", topic="SPEC-X-1")["docs"][0]["p"] == "docs/readiness.md"


def test_sdlc_context_gathers_the_chain_the_similar_tickets_and_owner(api):
    r = api.call("sdlc_context", ticket="ODSF-9")
    assert r["epic"] == ["ODSF-8"] and r["spec"] == ["docs/readiness.md"] and r["owner_role"] == "BE"
    assert r["similar"] == [{"t": "ODSF-7", "s": 0.4}] and r["commits"] == 1 and r["files"] == ["pkg/a.py"]
    assert "error" in api.call("sdlc_context", ticket="ODSF-404")


def test_trace_gives_the_chain_and_says_when_gate_zero_does_not_apply(api):
    r = api.call("trace", ticket="ODSF-8")
    assert r["gate0"].startswith("n/a")
    assert api.call("trace", ticket="ODSF-9")["epic"] == [{"id": "ODSF-8", "status": "OPEN"}]


def test_review_pack_maps_a_commit_to_changed_symbols_callers_and_tests(api):
    r = api.call("review_pack", rev=api.head)
    assert r["changed_symbols"] == ["pkg/a.py::save_record"]
    assert r["callers_outside"] == ["pkg/b.py::run", "tests/test_a.py::test_save"]
    assert r["tests"][0]["f"] == "tests/test_a.py" and r["tickets"] == ["ODSF-9"]
    assert r["docs"] == ["docs/readiness.md"] and r["warnings"] == ["DEV-06"] and "BE" in r["owners"]


def test_every_reply_says_whether_the_graph_is_stale(api):
    r = api.call("graph_status")
    assert r["_meta"]["stale"] is True and r["_meta"]["behind"] == 1


def test_the_index_is_cached_and_rebuilt_when_the_graph_changes(api, tmp_path):
    store = tmp_path / ".devkb"
    assert (store / service.CACHE_NAME).exists()
    again = service.load_index("TST", tmp_path, store)
    assert len(again.keys) == len(api.idx.keys)
    (store / "nodes.jsonl").write_text((store / "nodes.jsonl").read_text() + json.dumps(_node("z", "Symbol", "z.py::z")) + "\n")
    assert len(service.load_index("TST", tmp_path, store).keys) == len(api.idx.keys) + 1


def test_each_call_is_logged_with_its_size(api, tmp_path):
    api.call("graph_status")
    line = json.loads((tmp_path / ".devkb" / service.TELEMETRY_NAME).read_text().splitlines()[-1])
    assert line["tool"] == "graph_status" and line["bytes"] > 0 and line["ok"] is True
