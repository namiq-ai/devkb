"""ODSF-309: every process-API tool is fast warm, and the fixes keep the answers the same.

The fixture graph is the one ODSF-306's tests use. The expensive cases are counted, not timed, so these tests
do not depend on how fast the machine is.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from devkb import process_api, service  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402
from test_devkb_process_api_odsf306 import api  # noqa: E402,F401  (the fixture)

ALL_TOOLS = {"graph_status", "symbol", "outline", "uses", "search_docs", "callers", "callees", "tests_for", "tests_to_run", "impact", "owner",
             "sdlc_context", "lineage", "trace", "find_docs", "review_pack", "find_code", "history", "feature_brief",
             "bug_brief", "rca_trace", "refactor_scope", "explain_area", "flow_sequence", "test_items", "design_brief",
             "review_doc", "role_brief", "config"}


def _count_subprocess(monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []
    real = subprocess.run

    def spy(cmd, *a, **kw):
        calls.append(list(cmd))
        return real(cmd, *a, **kw)
    monkeypatch.setattr(process_api.subprocess, "run", spy)
    return calls


def test_the_benchmark_times_every_tool_and_reports_the_first_call_separately(api):
    out = process_api.bench_api(api, reps=3)
    assert set(out["per_tool"]) | set(out["skipped"]) == ALL_TOOLS
    assert set(out["per_tool"]) >= {"callers", "impact", "review_pack", "find_docs", "sdlc_context", "graph_status"}
    assert all("first_ms" in v and "p95_ms" in v and v["bytes"] > 0 for v in out["per_tool"].values())
    assert out["slowest"] in out["per_tool"]


def test_a_tool_with_no_valid_sample_is_skipped_not_counted_as_fast(api):
    api.idx.by_key = {k: v for k, v in api.idx.by_key.items() if k[0] != "Ticket"}
    out = process_api.bench_api(api, reps=2)
    assert {"sdlc_context", "lineage", "trace"} <= set(out["skipped"]) and "trace" not in out["per_tool"]


def test_review_pack_uses_one_moved_files_call_not_one_git_call_per_file(api, monkeypatch):
    calls = _count_subprocess(monkeypatch)
    api.call("review_pack", rev=api.head)
    diffs = [c for c in calls if c[:2] == ["git", "diff"]]
    assert not any("--quiet" in c for c in diffs), "the per-file drift check is gone"
    assert len(diffs) <= 2, diffs


def test_a_files_function_table_is_parsed_once_per_commit(api, monkeypatch):
    first = api._function_ranges(api.head, "pkg/a.py")
    calls = _count_subprocess(monkeypatch)
    assert api._function_ranges(api.head, "pkg/a.py") == first and calls == []
    assert any(name == "save_record" for _, _, name in first)


def test_gate_zero_status_is_computed_once_until_a_bmad_ticket_file_changes(api, tmp_path, monkeypatch):
    script = tmp_path / "_bmad" / "method" / "scripts" / "tickets.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake")
    store = tmp_path / "_bmad-output" / "init" / "tickets"
    store.mkdir(parents=True)
    entry = store / "e1.md"
    entry.write_text("x")
    status = {"tickets": [{"epic": "e1", "id": "2", "unknown": "still open"}]}

    class Done:
        stdout = json.dumps(status)
    ran: list[list[str]] = []
    monkeypatch.setattr(process_api.subprocess, "run", lambda cmd, *a, **kw: (ran.append(cmd), Done())[1])
    assert api._bmad_unknown_cached(tmp_path, "init/e1/2") == "still open"
    assert api._bmad_unknown_cached(tmp_path, "init/e1/2") == "still open" and len(ran) == 1
    assert api._bmad_unknown_cached(tmp_path, "init/e1/999") == "" and len(ran) == 1, "another entry reuses the same status"
    later = time.time() + 10
    os.utime(entry, (later, later))
    api._bmad_unknown_cached(tmp_path, "init/e1/2")
    assert len(ran) == 2, "a changed ticket file invalidates the cached status"
    assert api._bmad_unknown_cached(tmp_path, "not-a-ref") is None


def test_graph_status_reads_counts_computed_with_the_graph_not_a_scan(api):
    assert api.idx.type_count and api.idx.type_counts() is api.idx.type_count
    api.idx.types = None  # a scan over the nodes would now fail
    r = api.call("graph_status")
    assert r["symbols"] == 6 and r["specs"] == 2 and r["tickets"] == 3


def test_the_config_is_parsed_again_only_when_it_changes(api, tmp_path):
    first = api._config()
    assert api._config() is first
    cfg = json.loads((tmp_path / "pms.config.json").read_text())
    cfg["component_to_role"] = {"PMS": "FE"}
    (tmp_path / "pms.config.json").write_text(json.dumps(cfg, indent=2))
    assert api._config() is not first
    assert api.call("sdlc_context", ticket="ODSF-9")["owner_role"] == "FE"


def test_find_docs_through_the_index_ranks_exactly_like_scoring_every_document(tmp_path, monkeypatch):
    root = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "docs").mkdir()
    titles = ["Readiness gate rules", "Gate scopes and quality bars", "Role boundaries for agents", "Ontology governance",
              "Specification management", "Quality gate readiness", "LLM router data class", "Ticket filing standard",
              "Gate zero readiness checklist", "Unrelated notes"]
    nodes = []
    for n, title in enumerate(titles):
        (root / "docs" / f"doc{n}.md").write_text(f"# {title}\n\n## Details {n}\n")
        nodes.append({"uid": f"s{n}", "type": "Spec", "natural_key": f"docs/doc{n}.md", "source": "t",
                      "properties": {"title": title, "doc_type": "adr" if n % 2 else "design", "status": "accepted", "spec_id": f"SPEC-X-{n}"}})
    store = root / ".devkb"
    store.mkdir()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in nodes) + "\n")
    (store / "edges.jsonl").write_text("")
    (store / "manifest.json").write_text(json.dumps({"built_at": "t", "git_head": ""}))
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="X", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    docs = process_api.ProcessAPI("TST", telemetry=False)
    for q in ("readiness gate", "gate", "quality gate readiness", "role", "SPEC-X-3", "nothing matches this", "ontology governance gate"):
        assert [d["p"] for d in docs.find_docs(q)["docs"]] == docs._find_docs_scan(q), q
    assert [d["p"] for d in docs.find_docs("gate", kinds=["adr"])["docs"]] == docs._find_docs_scan("gate", kinds=["adr"])


def test_staleness_never_makes_a_call_wait_for_git_after_the_first(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@e.x", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "a"], cwd=tmp_path, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    s = service.Staleness(tmp_path, head, ttl=0.0)
    assert s.check()[0] is False
    subprocess.run(["git", "-c", "user.email=t@e.x", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "b"], cwd=tmp_path, check=True)
    s.check()  # returns the old answer at once and refreshes in the background
    deadline = time.time() + 5
    while time.time() < deadline and not s.check()[0]:
        time.sleep(0.05)
    assert s.check()[0] is True and s.check()[2] == 1


def test_a_reply_is_trimmed_to_its_byte_budget_and_says_what_it_left_out():
    reply = {"symbol": "a.py::hub", "n": [60, 55],
             "direct": [f"pkg/module_{i}.py::function_number_{i}" for i in range(60)],
             "indirect": [f"pkg/other_{i}.py::another_function_{i}" for i in range(55)]}
    fitted = process_api._fit(dict(reply), budget=1500)
    assert len(json.dumps(fitted, separators=(",", ":"))) <= 1500
    assert fitted["truncated"] is True and fitted["n"] == [60, 55], "totals stay exact"
    assert fitted["omitted"]["direct"] + len(fitted["direct"]) == 60 and fitted["omitted"]["indirect"] + len(fitted["indirect"]) == 55
    small = {"symbol": "a.py::f", "direct": ["a", "b"]}
    assert process_api._fit(dict(small)) == small, "a reply that fits is untouched"


def test_every_tool_reply_stays_under_the_byte_target_even_for_a_hub_symbol(api):
    for tool, kw in (("callers", {"symbol": "save_record", "depth": 3}), ("impact", {"files": ["pkg/a.py"], "depth": 3}),
                     ("find_docs", {"topic": "readiness"}), ("review_pack", {"rev": api.head})):
        assert len(json.dumps(api.call(tool, **kw), separators=(",", ":"))) < process_api.REPLY_TARGET_BYTES, tool
