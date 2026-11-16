"""ODSF-307: the process API is reachable as MCP tools and a skill says when to use each one."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import process_api  # noqa: E402

SERVER = (_REPO_ROOT / "devkb" / "mcp_server.py").read_text()
SKILL = (_REPO_ROOT / "skills" / "devkb-sdlc" / "SKILL.md").read_text()
TOOLS = re.findall(r"    @tool\n    def (\w+)\(", SERVER)


def test_the_server_declares_its_read_only_tools_with_one_sentence_descriptions():
    assert len(TOOLS) == 25 and len(set(TOOLS)) == 25  # 12 single-question (config: ODSF-312), 7 developer-task (ODSF-310), 5 document and role (ODSF-311), pack
    assert "readOnlyHint=True" in SERVER and "destructiveHint=False" in SERVER
    for name in TOOLS:
        doc = re.search(rf"def {name}\(.*?\n\s+\"\"\"(.*?)\"\"\"", SERVER, re.S).group(1)
        assert len(doc) <= 190, f"{name}: a tool description is paid for in every model turn"


def test_every_tool_is_a_method_of_the_process_api():
    from devkb.packs import Packer
    for name in TOOLS:
        if name == "pack":  # served by the packs module, one method per kind
            assert all(hasattr(Packer, k) for k in ("file", "refactor", "change", "error", "pr", "ticket"))
            continue
        assert hasattr(process_api.ProcessAPI, name), name


def test_the_skills_name_every_tool_that_serves_a_stage_and_the_umbrella_has_its_frontmatter():
    assert SKILL.startswith("---\nname: devkb-sdlc\ndescription: ")
    every_skill = "\n".join(p.read_text() for p in (_REPO_ROOT / "skills").glob("devkb-*/SKILL.md"))
    for name in TOOLS:
        if name != "graph_status":
            assert f"`{name}`" in every_skill, f"{name} is not mapped to any developer task or stage in the skills"
    for stage in ("S0", "S1", "S4", "S6", "S7", "S8", "S9"):
        assert stage in SKILL
    assert "_meta.stale" in SKILL and "make gate-0" in SKILL


def test_the_project_is_inferred_from_the_working_directory_deepest_match_first(tmp_path, monkeypatch):
    outer, inner = tmp_path / "outer", tmp_path / "outer" / "inner"
    inner.mkdir(parents=True)
    reg = tmp_path / "projects.json"
    reg.write_text(json.dumps({"projects": [{"code": "OUT", "repo": str(outer)}, {"code": "IN", "repo": str(inner)}]}))
    from devkb import project_context
    monkeypatch.setattr(project_context, "PROJECTS_JSON", reg)
    assert process_api.project_for(inner / "x") == "IN"
    assert process_api.project_for(outer) == "OUT"
    assert process_api.project_for(tmp_path / "elsewhere") is None


def test_the_built_server_lists_the_tools_with_read_only_annotations():
    pytest.importorskip("mcp.server.fastmcp")
    import asyncio
    import importlib.util

    spec = importlib.util.spec_from_file_location("devkb_mcp_server", _REPO_ROOT / "devkb" / "mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = module.build(object())  # tools are only declared here; no call is made
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == sorted(TOOLS)
    assert all(t.annotations.readOnlyHint for t in tools)


def test_pack_is_a_tool_in_dev_and_lean_pack_and_lean_stays_as_measured():
    pytest.importorskip("mcp.server.fastmcp")
    import importlib.util

    spec = importlib.util.spec_from_file_location("devkb_mcp_server", _REPO_ROOT / "devkb" / "mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "pack" in module.TOOLSETS["dev"] and "pack" in module.TOOLSETS["lean-pack"]
    assert module.TOOLSETS["lean"] == ["rca_trace", "impact", "callers", "tests_for", "tests_to_run", "review_pack", "config"]
    assert module.TOOLSETS["lean-pack"] == module.TOOLSETS["lean"] + ["pack"]
