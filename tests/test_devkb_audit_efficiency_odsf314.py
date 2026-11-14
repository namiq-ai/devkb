"""ODSF-314: the graph keeps the edges that answer chain-and-join questions, measured against source truth.

Each test pins one change the OCO audit (docs/graph-audit-odsf314.md) justified."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import audit, build_symbols, ts_symbols  # noqa: E402
from devkb.extractors import files_tests, members, ticket_similarity  # noqa: E402
from devkb.model import DevKBGraph  # noqa: E402


def test_a_bulk_commit_keeps_its_size_not_one_touches_edge_per_file():
    assert files_tests.is_bulk(["f"] * (files_tests.BULK_COMMIT_FILES + 1))
    assert not files_tests.is_bulk(["f"] * files_tests.BULK_COMMIT_FILES)


def test_ticket_marker_tested_by_comes_only_from_code_files_with_honest_confidence():
    assert files_tests._CODE_FILE.search("webapp/backend/app/main.py") and files_tests._CODE_FILE.search("web/a.tsx")
    for not_code in (".coveragerc", "sdp/orchestrator/status/BE.md", "package.json"):
        assert not files_tests._CODE_FILE.search(not_code), not_code
    assert files_tests._TEST_PATH.search("tests/test_x.py") and files_tests._TEST_PATH.search("web/a.test.ts")
    assert files_tests._MARKER_CONFIDENCE < 0.5 <= 0.95, "below every import-resolved TESTED_BY"


def test_similar_to_keeps_each_tickets_top_neighbours_with_the_score_as_confidence(monkeypatch):
    n = ticket_similarity.TOP_NEIGHBOURS + 4
    g = DevKBGraph()
    for i in range(n):
        t = f"T-{i}"
        g.add_node("Ticket", t, "t")
        g.add_node("Commit", f"c{i}", "t")
        g.add_edge("REFERENCES", "Commit", f"c{i}", "Ticket", t, "t")
        for f in ["shared.py"] + [f"own{i}.py"] * (i % 3 + 1) + [f"f{j}.py" for j in range(i)]:
            g.add_node("File", f, "t")
            g.add_edge("TOUCHES", "Commit", f"c{i}", "File", f, "t")
    out = ticket_similarity.extract(type("C", (), {"code": "T"})(), g)
    per = {}
    for e in out.edges("SIMILAR_TO"):
        per.setdefault(e.src, []).append(e)
        assert 0 < e.confidence < 1 and e.confidence == e.extra["weighted_score"]
    assert per and max(len(v) for v in per.values()) <= ticket_similarity.TOP_NEIGHBOURS


def test_the_products_own_files_get_no_in_repo_and_a_members_do():
    g = DevKBGraph()
    g.add_node("File", "app/a.py", "t")
    g.add_node("File", "MEM:src/b.py", "t")
    members.link_repository(g, "PRD")
    members.link_repository(g, "MEM", role="client", only_prefix="MEM:")
    assert {(e.src, e.dst) for e in g.edges("IN_REPO")} == {("MEM:src/b.py", "MEM")}
    assert {n.natural_key for n in g.nodes("Repository")} == {"PRD", "MEM"}


def test_frontend_calls_built_with_templates_wrappers_and_builders_reach_their_route_handler(tmp_path):
    files = {
        "backend/app/routers/jobs.py": ("from fastapi import APIRouter\nrouter = APIRouter(prefix='/api/v1')\n\n\n"
                                        "@router.get('/jobs/{job_id}')\ndef get_job(job_id: str):\n    return job_id\n\n\n"
                                        "@router.post('/quality/issues/{issue_id}/acknowledge')\ndef ack(issue_id: str):\n    return issue_id\n\n\n"
                                        "@router.get('/quality/score')\ndef score():\n    return 1\n"),
        "web/lib/urls.ts": "export function ackUrl(id: string): string {\n  return `/api/v1/quality/issues/${encodeURIComponent(id)}/acknowledge`;\n}\n",
        "web/lib/api.ts": ('const BASE = "/api/v1";\n\nasync function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {\n'
                           "  const res = await fetch(`${BASE}${path}`, init);\n  return res.json();\n}\n\n"
                           'export function loadScore() {\n  return apiFetch<number>("/quality/score");\n}\n'),
        "web/app/page.tsx": ("import { ackUrl } from '../lib/urls';\n\nexport async function loadJob(id: string) {\n"
                             "  return fetch(`/api/v1/jobs/${id}`);\n}\n\nexport async function acknowledge(id: string) {\n"
                             '  return fetch(ackUrl(id), { method: "POST" });\n}\n'),
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    g = build_symbols.extract(tmp_path)
    api = {(e.src, e.dst) for e in g.edges("CALLS_API")}
    assert ("web/app/page.tsx::loadJob", "backend/app/routers/jobs.py::get_job") in api, "template literal"
    assert ("web/app/page.tsx::acknowledge", "backend/app/routers/jobs.py::ack") in api, "a builder from another file"
    assert ("web/lib/api.ts::loadScore", "backend/app/routers/jobs.py::score") in api, "a wrapper's module prefix"
    assert ts_symbols.normalise_path("https://h.example/api/v1/x/${id}?q=1", {}) == "/api/v1/x/{}"
    assert ts_symbols.route_shape("/api/v1/jobs/{job_id}") == ts_symbols.route_shape("/api/v1/jobs/{}")


def test_the_audit_reports_shares_and_fails_its_floor_on_a_noisy_graph(tmp_path):
    def n(t, k):
        return {"uid": f"{t}:{k}", "type": t, "natural_key": k, "source": "t", "properties": {}}
    nodes = [n("Commit", "c1"), n("File", "a.py"), n("Symbol", "a.py::f"), n("Symbol", "a.py::g")]
    edges = [{"from_uid": "Commit:c1", "to_uid": "File:a.py", "verb": "TOUCHES", "properties": {"source": "git", "confidence": 1.0}}] * 9
    edges += [{"from_uid": "Symbol:a.py::f", "to_uid": "Symbol:a.py::g", "verb": "CALLS", "properties": {"source": "ast", "confidence": 0.8}}]
    (tmp_path / "nodes.jsonl").write_text("\n".join(json.dumps(x) for x in nodes) + "\n")
    (tmp_path / "edges.jsonl").write_text("\n".join(json.dumps(x) for x in edges) + "\n")
    r = audit.audit(tmp_path)
    assert r["edges"] == 10 and r["verbs"]["TOUCHES"]["share"] == 0.9 and r["low_value_share"] == 0.9
    assert r["verbs"]["CALLS"]["tool_reads"] > 0 and "CALLS" in audit.render(r)
    assert r["low_value_share"] > audit.FLOORS["max_low_value_share"], "the floor rejects a graph that is mostly history"
