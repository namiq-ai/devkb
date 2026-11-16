"""ODSF-310: one call per kind of development work, each checked against a graph whose answers are known."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import process_api  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _n(uid, typ, key, **p):
    return {"uid": uid, "type": typ, "natural_key": key, "source": "t", "properties": p}


def _e(a, verb, b, **p):
    return {"from_uid": a, "to_uid": b, "verb": verb, "properties": p}


@pytest.fixture
def api(tmp_path, monkeypatch):
    root = tmp_path
    _git(root, "init", "-q")
    for k, v in (("user.email", "t@example.com"), ("user.name", "T")):
        _git(root, "config", k, v)
    for rel, text in {"pkg/store.py": "def save_record(x):\n    raise ValueError('record is invalid')\n", "pkg/api.py": "def post_record():\n    pass\n",
                      "web/page.py": "def show():\n    pass\n", "tests/test_store.py": "def test_save():\n    pass\n",
                      "docs/records.md": "# Records design\n\n## Saving a record\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    (root / "sdp/process/roles").mkdir(parents=True)
    (root / "sdp/process/roles/be.md").write_text("### OWN:\n```\npkg/\n```\n### DO NOT TOUCH:\n```\nweb/\n```\n")
    (root / "sdp/process/roles/fe.md").write_text("### OWN:\n```\nweb/\n```\n### DO NOT TOUCH:\n```\npkg/\n```\n")
    (root / "pms.config.json").write_text(json.dumps({"role_profiles": {"BE": "be.md", "FE": "fe.md"}, "component_to_role": {"PMS": "BE"},
                                                       "subsystems": [{"key": "pkg", "path": "pkg"}]}))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "ODSF-5: fix empty record names")
    head = _git(root, "rev-parse", "HEAD")
    nodes = [
        _n("s1", "Symbol", "pkg/store.py::save_record", kind="function", line_start=1, line_end=2, complexity=4, is_public=True,
           docstring_summary="Save a record to the store and reject an invalid one"),
        _n("s2", "Symbol", "pkg/api.py::post_record", kind="function", line_start=1, line_end=2, complexity=1, is_public=True,
           docstring_summary="HTTP handler that saves a record"),
        _n("s3", "Symbol", "web/page.py::show", kind="function", line_start=1, line_end=2, complexity=1, is_public=True, docstring_summary="Render the page"),
        _n("s4", "Symbol", "tests/test_store.py::test_save", kind="function", line_start=1, line_end=2),
        _n("e1", "Endpoint", "POST /records", method="POST", path="/records", owner_symbol="pkg/api.py::post_record"),
        _n("er1", "ErrorSignature", "sig1", kind="raised", label="ValueError", message_template="record {} is invalid"),
        _n("t1", "Ticket", "ODSF-5", title="Saving a record with an empty name crashes the store", ticket_type="BUG", status="DONE", component="PMS", assignee="BE"),
        _n("t2", "Ticket", "ODSF-9", title="Saving a record fails with record is invalid", ticket_type="BUG", status="OPEN", component="PMS", assignee="BE"),
        _n("t3", "Ticket", "ODSF-7", title="Add a records export", ticket_type="FEATURE", status="DONE", component="PMS", assignee="BE"),
        _n("sp1", "Spec", "docs/records.md", title="Records design", doc_type="design", status="accepted", spec_id="SPEC-R-1"),
        _n("f1", "File", "pkg/store.py"), _n("f2", "File", "pkg/api.py"),
        _n("c1", "Commit", "c" * 40, short_hash="aaaaaaaaaa", subject="fix(ODSF-5): reject an empty record name", date="2026-11-02"),
        _n("c2", "Commit", "d" * 40, short_hash="bbbbbbbbbb", subject="feat(ODSF-7): export records", date="2026-10-01"),
        _n("fl1", "Flow", "flow:endpoint:pkg/api.py::post_record", touch_point_kind="endpoint", step_count=2),
    ]
    edges = [
        _e("s2", "CALLS", "s1"), _e("s4", "CALLS", "s1"), _e("s3", "CALLS", "s2"), _e("s3", "CALLS", "s1"), _e("s1", "RAISES", "er1"),
        _e("c1", "TOUCHES", "f1"), _e("c2", "TOUCHES", "f1"), _e("c2", "TOUCHES", "f2"), _e("c1", "REFERENCES", "t1"), _e("c2", "REFERENCES", "t3"),
        _e("fl1", "STEP", "s2"), _e("fl1", "STEP", "s1"), _e("sp1", "DOCUMENTS", "t3"),
    ]
    store = root / ".devkb"
    store.mkdir()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(x) for x in nodes) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(x) for x in edges) + "\n")
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-13T00:00:00+00:00", "git_head": head}))
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="ODSF", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    return process_api.ProcessAPI("TST", telemetry=False)


def test_find_code_matches_names_and_docstrings_and_ignores_filler_words(api):
    r = api.call("find_code", query="add a function to save the records")
    assert r["code"][0]["k"] == "pkg/store.py::save_record" and r["code"][0]["callers"] == 2
    assert all("tests/" not in c["k"] for c in r["code"]), "tests are not suggested as the place to build"
    assert api.call("find_code", query="the and for")["code"] == []
    assert [c["k"] for c in api.call("find_code", query="record", under="web/")["code"]] == []


def test_history_lists_newest_first_and_names_the_tickets(api):
    r = api.call("history", files=["pkg/store.py"])
    assert [c["h"] for c in r["commits"]] == ["aaaaaaaa", "bbbbbbbb"] and r["commits"][0]["t"] == ["ODSF-5"]


def test_rca_trace_goes_from_the_message_to_the_raiser_the_entry_point_and_the_recent_change(api):
    r = api.call("rca_trace", symptom="record is invalid")
    assert r["matched_by"] == "error message" and r["signatures"][0]["msg"] == "record {} is invalid"
    assert r["raisers"] == ["pkg/store.py::save_record"]
    assert "pkg/api.py::post_record" in r["entry_points"] or any(c["k"] == "pkg/api.py::post_record" for c in r["chain"])
    assert r["recent"][0]["h"] == "aaaaaaaa" and r["tests"][0]["f"] == "tests/test_store.py"
    assert r["flows"] == ["flow:endpoint:pkg/api.py::post_record"]
    assert "error" in api.call("rca_trace", symptom="completely unrelated zebra words")


def test_rca_trace_falls_back_to_code_names_when_no_message_matches(api):
    r = api.call("rca_trace", symptom="render the page")
    assert r["matched_by"].startswith("code name") and r["raisers"] == ["web/page.py::show"]
    # plurals and -ing forms match: "saving records" reaches the error message "record {} is invalid" and `save_record`
    assert api.call("rca_trace", symptom="saving records")["raisers"] == ["pkg/store.py::save_record"]


def test_bug_brief_gives_suspects_history_similar_fixed_bugs_and_never_the_ticket_itself(api):
    r = api.call("bug_brief", ticket="ODSF-9")
    assert r["suspects"] == ["pkg/store.py::save_record"] and r["owner_role"] == "BE"
    assert [s["t"] for s in r["similar_bugs"]] == ["ODSF-5"] and r["similar_bugs"][0]["files"] == ["pkg/store.py"]
    assert r["recent"] and r["tests"]
    assert "error" in api.call("bug_brief") and "error" in api.call("bug_brief", ticket="ODSF-404")
    assert api.call("bug_brief", text="record is invalid")["suspects"] == ["pkg/store.py::save_record"]


def test_feature_brief_returns_code_docs_similar_work_owner_boundary_and_a_test_command(api):
    r = api.call("feature_brief", goal="save records to the store")
    assert r["code"][0]["k"] == "pkg/store.py::save_record" and r["docs"][0]["p"] == "docs/records.md"
    assert [s["t"] for s in r["similar_work"]] == ["ODSF-5", "ODSF-7"] or {s["t"] for s in r["similar_work"]} >= {"ODSF-7"}
    assert "pkg/store.py" in r["owners"]["BE"] and r["boundary"]["forbidden_for"] == ["FE"]
    assert r["run"].startswith("python3 -m pytest") and "tests/test_store.py" in r["run"]
    assert "ODSF-9" not in {s["t"] for s in api.call("feature_brief", goal="records", ticket="ODSF-9")["similar_work"]}


def test_explain_area_orders_symbols_by_how_much_depends_on_them(api):
    r = api.call("explain_area", path="pkg")
    assert r["files"] == 2 and r["key_symbols"][0]["k"] == "pkg/store.py::save_record"
    assert r["endpoints"] == ["POST /records"] and r["owners"] == {"BE": ["pkg/api.py", "pkg/store.py"]}
    assert "error" in api.call("explain_area", path="nowhere")
    top = r["key_symbols"][0]
    # the workflow benchmark found agents reading a test-free count as "callers"; both counts are named now
    assert (top["prod_callers"], top["test_callers"]) == (2, 1) and "callers" not in top and "prod_callers" in r["ranked_by"]


def test_refactor_scope_lists_callers_by_file_tests_and_the_files_a_role_may_not_edit(api):
    r = api.call("refactor_scope", target="save_record", role="FE")
    assert {c["f"] for c in r["caller_files"]} == {"pkg/api.py", "web/page.py"} and r["test_files"] == ["tests/test_store.py"]
    assert r["blocked_files"] == ["pkg/api.py"], "FE must not touch pkg/, but may edit web/"
    assert r["public"] is True and r["max_complexity"] == 4 and r["run"].startswith("python3 -m pytest")
    assert api.call("refactor_scope", target="save_record", role="BE")["blocked_files"] == ["web/page.py"], "BE must not touch web/"
    assert api.call("refactor_scope", target="pkg/store.py")["symbols"] == 1


def test_every_developer_skill_names_a_real_tool_and_stays_short():
    skills = sorted((_REPO_ROOT / "skills").glob("devkb-*/SKILL.md"))
    assert len(skills) >= 12
    server = (_REPO_ROOT / "devkb" / "mcp_server.py").read_text()
    tools = set(re.findall(r"    def (\w+)\(", server)) & set(dir(process_api.ProcessAPI))
    for path in skills:
        text = path.read_text()
        assert text.startswith(f"---\nname: {path.parent.name}\ndescription: "), path
        limit = 450 if path.parent.name == "devkb-sdlc" else 260
        assert len(text.split()) <= limit, f"{path.parent.name}: a skill is paid for in every session that loads it"
        if path.parent.name != "devkb-sdlc":
            assert any(f"`{tool}`" in text for tool in tools), path


def test_the_toolsets_register_exactly_the_tools_they_name():
    server = (_REPO_ROOT / "devkb" / "mcp_server.py").read_text()
    registered = set(re.findall(r"    @tool\n    def (\w+)\(", server))
    ns: dict = {}
    exec(re.search(r"CORE = .*?TOOLSETS = \{.*?\}\n", server, re.S).group(0), ns)
    assert set(ns["TOOLSETS"]["all"]) == registered and set(ns["CORE"]) | set(ns["WORKFLOW"]) | set(ns["DOCS"]) | {"pack"} == registered
    assert set(ns["TOOLSETS"]["workflow"]) <= registered and set(ns["WORKFLOW"]) <= set(ns["TOOLSETS"]["workflow"])
