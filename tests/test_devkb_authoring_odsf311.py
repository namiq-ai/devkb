"""ODSF-311: documents (designs, sequence diagrams, test specifications and their review) and role session starts.

The fixture graph has one recorded flow, one test-case register, four role profiles and a design document seeded
with known mistakes, so every expected answer is known before the code runs.
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

from devkb import process_api, startup  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402

REVIEW_ME = """# Records functional design

## Purpose and users
Saving goes through `save_record` in pkg/store.py, and the old path was pkg/missing.py.
It also calls `ghost_function()`, and stores a `TestCase` with a `first_seen` field. See ODSF-5 and ODSF-999, and SPEC-R-1 and SPEC-R-99.

## Interfaces
Nothing else is described here.
"""


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
    files = {
        "pkg/store.py": "def save_record(x):\n    raise ValueError('record is invalid')\n",
        "pkg/api.py": "def post_record():\n    pass\n", "web/page.py": "def show():\n    pass\n",
        "tests/test_store.py": "def test_save():\n    pass\n",
        "docs/records.md": "# Records design\n\n## Purpose and users\n\n## Interfaces\n", "docs/draft.md": "# Draft\n",
        "docs/review-me.md": REVIEW_ME,
        "design/x03.json": json.dumps({"cases": {"X-1": {"title": "saving works", "binding": {"node": "tests/test_store.py::test_save"}}}}),
        "st.config.json": json.dumps({"code": "TST", "product": "t", "register": "design/x03.json"}),
    }
    roles = {"be.md": ("pkg/", "web/", "Own the records service."), "fe.md": ("web/", "pkg/", "Own the page."),
             "qa.md": ("tests/", "pkg/", "Prove it works."), "tl.md": ("docs/", "", "Decide.")}
    for name, (own, dnt, mission) in roles.items():
        files[f"sdp/process/roles/{name}"] = (f"**Mission**: {mission}\n**Decides**: what is in scope.\n\n### OWN:\n```\n{own}\n```\n"
                                               + (f"### DO NOT TOUCH:\n```\n{dnt}\n```\n" if dnt else ""))
    files["pms.config.json"] = json.dumps({"role_profiles": {"BE": "be.md", "FE": "fe.md", "QA": "qa.md", "TL": "tl.md"},
                                           "component_to_role": {"PMS": "BE"}, "subsystems": [{"key": "pkg", "path": "pkg"}]})
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")
    head = _git(root, "rev-parse", "HEAD")
    nodes = [
        _n("s1", "Symbol", "pkg/store.py::save_record", kind="function", line_start=1, line_end=2, complexity=4, is_public=True,
           docstring_summary="Save a record to the store"),
        _n("s2", "Symbol", "pkg/api.py::post_record", kind="function", line_start=1, line_end=2, complexity=1, is_public=True,
           docstring_summary="HTTP handler that saves a record"),
        _n("s3", "Symbol", "web/page.py::show", kind="function", line_start=1, line_end=2, complexity=1),
        _n("s4", "Symbol", "tests/test_store.py::test_save", kind="function", line_start=1, line_end=2),
        _n("e1", "Endpoint", "POST /records", method="POST", path="/records", owner_symbol="pkg/api.py::post_record"),
        _n("er1", "ErrorSignature", "sig1", kind="raised", label="ValueError", message_template="record {} is invalid"),
        _n("fl1", "Flow", "flow:endpoint:pkg/api.py::post_record", touch_point_kind="endpoint", step_count=2),
        _n("t5", "Ticket", "ODSF-5", title="Empty names crash the store", ticket_type="BUG", status="DONE", assignee="BE", priority="P1"),
        _n("t6", "Ticket", "ODSF-6", title="Records can be exported", ticket_type="STORY", status="OPEN", assignee="BE", priority="P1"),
        _n("t8", "Ticket", "ODSF-8", title="Test the export", ticket_type="TASK", status="REVIEW", assignee="QA", priority="P2"),
        _n("sp1", "Spec", "docs/records.md", title="Records design", doc_type="specification", status="accepted", spec_id="SPEC-R-1"),
        _n("sp2", "Spec", "docs/draft.md", title="Draft", doc_type="design", status="draft", spec_id="SPEC-R-2"),
        _n("f1", "File", "pkg/store.py"),
        _n("c1", "Commit", "c" * 40, short_hash="aaaaaaaaaa", subject="fix(ODSF-5): reject empty names", date="2999-12-01"),
    ]
    edges = [_e("s2", "CALLS", "s1"), _e("s4", "CALLS", "s1"), _e("s1", "RAISES", "er1"),
             _e("fl1", "STEP", "s2", sequence=1), _e("fl1", "STEP", "s1", sequence=2), _e("c1", "TOUCHES", "f1")]
    store = root / ".devkb"
    store.mkdir()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(x) for x in nodes) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(x) for x in edges) + "\n")
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-13T00:00:00+00:00", "git_head": head}))
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="ODSF", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    return process_api.ProcessAPI("TST", telemetry=False)


def test_flow_sequence_turns_the_recorded_call_order_into_messages_and_mermaid(api):
    for entry in ("POST /records", "post_record", "flow:endpoint:pkg/api.py::post_record"):
        r = api.call("flow_sequence", entry=entry)
        assert r["messages"] == ["pkg/api.py::post_record -> pkg/store.py::save_record"], entry
        assert r["participants"] == ["pkg/api.py", "pkg/store.py"]
    assert "sequenceDiagram" in r["mermaid"] and "p0->>p1: save_record" in r["mermaid"]
    assert "error" in api.call("flow_sequence", entry="show")


def test_test_items_come_from_raised_errors_endpoints_and_untested_branches(api):
    r = api.call("test_items", area="pkg")
    kinds = {(it["kind"], it["target"]) for it in r["items"]}
    assert ("negative", "pkg/store.py::save_record") in kinds and ("contract", "pkg/api.py::post_record") in kinds
    assert r["items"][0]["covered"] is False, "uncovered items come first"
    assert r["untested"] == 1 and r["register_cases"] == ["X-1"] and "tests/test_store.py" in r["run"]


def test_design_brief_gives_the_outline_the_facts_and_the_next_spec_id(api):
    r = api.call("design_brief", kind="functional", topic="save records")
    assert r["outline"] == process_api.TEMPLATES["functional"] and r["next_spec_id"] == "SPEC-R-003"
    assert r["docs"][0]["p"] == "docs/records.md" and "Interfaces" in r["docs"][0]["heads"]
    assert "POST /records" in r["facts"]["interfaces"] and r["facts"]["errors"] == ["ValueError: record {} is invalid"]
    assert r["facts"].get("flow") is None
    seq = api.call("design_brief", kind="sequence diagram".replace(" ", "_"), topic="save records")
    assert seq["kind"] == "sequence" and seq["facts"]["flow"]["messages"]
    assert api.call("design_brief", kind="arch", topic="records")["kind"] == "architecture"
    assert "items" in api.call("design_brief", kind="test", topic="pkg")["facts"]["test_items"]
    assert "error" in api.call("design_brief", kind="poem", topic="records")


def test_review_doc_finds_broken_references_drift_omissions_and_missing_sections(api):
    r = api.call("review_doc", path="docs/review-me.md", kind="functional")
    assert r["broken"]["paths"] == ["pkg/missing.py"] and r["broken"]["symbols"] == ["ghost_function"]
    assert r["broken"]["tickets"] == ["ODSF-999"] and r["broken"]["doc_ids"] == ["SPEC-R-99"]
    assert {"f": "pkg/store.py", "newer_commits": 1} in r["drift"], "the code changed after the document was written"
    assert "Acceptance criteria" in r["missing_sections"] and "Purpose and users" not in r["missing_sections"]
    ts = api.call("review_doc", path="docs/review-me.md", kind="test_spec")
    assert any("POST /records" in it for it in ts["untested_items_not_in_doc"])
    assert "error" in api.call("review_doc", path="docs/nope.md")


def test_role_brief_starts_each_role_with_its_own_territory_work_code_and_skills(api):
    be = api.call("role_brief", role="be")
    assert be["role"] == "BE" and be["profile"]["mission"] == "Own the records service."
    assert be["territory"] == {"own": ["pkg/"], "forbidden": ["web/"]}
    assert be["work"]["counts"] == {"DONE": 1, "OPEN": 1} and be["work"]["open"][0]["t"] == "ODSF-6"
    assert be["area"]["key_symbols"][0]["k"] == "pkg/store.py::save_record" and be["area"]["endpoints"] == ["POST /records"]
    assert "devkb-feature" in be["ask"]
    tl = api.call("role_brief", role="TL")
    assert tl["extras"]["review_queue"] == ["ODSF-8"] and tl["extras"]["draft_specs"] == 1
    assert "devkb-testspec" in api.call("role_brief", role="QA")["ask"]
    assert "known: BE, FE, QA, TL" in api.call("role_brief", role="nobody")["error"]


def test_startup_file_is_short_and_carries_the_brief_into_the_first_turn(api, tmp_path):
    path = startup.write(api, "BE", tmp_path / "startup")
    text = path.read_text()
    assert path.name == "BE.md" and text.startswith("# Session start: BE")
    for must in ("## Territory", "`pkg/`", "`web/`", "ODSF-6", "pkg/store.py::save_record", "python3 -m pytest", "devkb-feature"):
        assert must in text, must
    assert len(text.split()) < 600, "a startup file is paid for in every session that loads it"
    assert startup.write(api, "nobody", tmp_path / "startup") is None


def test_document_tool_replies_stay_under_the_byte_target(api):
    for tool, kw in (("design_brief", {"kind": "architecture", "topic": "records store page"}), ("review_doc", {"path": "docs/review-me.md"}),
                     ("test_items", {"area": "pkg"}), ("role_brief", {"role": "BE"}), ("flow_sequence", {"entry": "POST /records"})):
        assert len(json.dumps(api.call(tool, **kw), separators=(",", ":"))) < process_api.REPLY_TARGET_BYTES, tool


def test_role_territory_reads_both_profile_dialects():
    flat = "### OWN:\n```\npkg/\nweb/page.py   \u2190 the page\n```\n"
    tree = ("### YOU OWN (read + write freely):\n```\nscripts/\n  extractors/extract_*.py   \u2190 all extractors\n"
            "  build_graph.py\nworkspace/graph/\n```\n")
    assert process_api._lines(process_api._OWN.search(flat).group(1)) == ["pkg/", "web/page.py"]
    assert process_api._lines(process_api._OWN.search(tree).group(1)) == ["scripts/extractors/extract_", "scripts/build_graph.py", "workspace/graph/"]
    assert process_api._OWN.search("### TL OWNS (authoritative):\n```\ndesign/\n```\n").group(1) == "design/\n"


