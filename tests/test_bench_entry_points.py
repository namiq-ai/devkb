"""The two ways an agent reaches devkb, and what a benchmark run records of them: the shell entry point (a `devkb ...` command, taught by the policy files,
and the guardrail hook that answers before a grep) and the tool entry point (an `mcp__devkb*` tool in the model's own tool list). The `both` arm has all
three; `main` has no tool; `none` has none; each run records what it really had and what differs from its arm."""
import importlib
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = importlib.import_module("storybench")


def _stream(tmp_path, tools):
    p = tmp_path / "stream.jsonl"
    p.write_text(json.dumps({"type": "system", "subtype": "init", "tools": tools, "mcp_servers": []}) + "\n" + json.dumps({"type": "assistant"}) + "\n")
    return p


def _checkout(tmp_path, hook=True, policy=True):
    w = tmp_path / "w"
    (w / ".claude").mkdir(parents=True)
    if hook:
        (w / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Grep|Bash", "hooks": [
            {"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/devkb_guardrail.py\""}]}]}}))
    if policy:
        (w / "AGENTS.md").write_text("<!-- devkb:begin -->\n## devkb: ask the graph\n<!-- devkb:end -->\n")
    return w


def _env(tmp_path, guardrail="1"):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "devkb").write_text("#!/bin/sh\n")
    (b / "devkb").chmod((b / "devkb").stat().st_mode | stat.S_IXUSR)
    return {"PATH": f"{b}:{os.environ['PATH']}", "DEVKB_GUARDRAIL": guardrail}


BASE_TOOLS = ["Bash", "Grep", "Read", "Edit"]
MCP_TOOLS = ["mcp__devkb__symbol", "mcp__devkb__pack"]


def test_the_arms_design_which_entry_points_each_has():
    assert pb.ENTRY_POINTS["both"] == (True, True, True)            # shell, hook, tool
    assert pb.ENTRY_POINTS["main"] == (True, True, False) and pb.ENTRY_POINTS["none"] == (False, False, False)
    assert pb.ENTRY_POINTS["userinit"] == (True, False, True)


def test_the_tool_list_is_read_from_the_streams_init_event(tmp_path):
    assert pb.init_tools(_stream(tmp_path, BASE_TOOLS + MCP_TOOLS)) == BASE_TOOLS + MCP_TOOLS
    assert pb.init_tools(tmp_path / "missing.jsonl") == []


def test_a_main_run_has_the_shell_and_the_hook_but_no_tool(tmp_path):
    ep = pb.entry_points_observed("main", _checkout(tmp_path), _env(tmp_path), _stream(tmp_path, BASE_TOOLS))
    assert (ep["shell"], ep["hook"], ep["tool"], ep["policy"]) == (True, True, False, True) and pb.entry_point_problems("main", ep) == []


def test_a_both_run_has_all_three(tmp_path):
    ep = pb.entry_points_observed("both", _checkout(tmp_path), _env(tmp_path), _stream(tmp_path, BASE_TOOLS + MCP_TOOLS))
    assert (ep["shell"], ep["hook"], ep["tool"]) == (True, True, True) and pb.entry_point_problems("both", ep) == []


def test_a_both_run_whose_tool_list_lacks_devkb_is_reported(tmp_path):
    ep = pb.entry_points_observed("both", _checkout(tmp_path), _env(tmp_path), _stream(tmp_path, BASE_TOOLS))
    assert any(p.startswith("tool: expected present") for p in pb.entry_point_problems("both", ep))


def test_a_main_run_that_was_given_a_devkb_tool_is_reported(tmp_path):
    ep = pb.entry_points_observed("main", _checkout(tmp_path), _env(tmp_path), _stream(tmp_path, BASE_TOOLS + MCP_TOOLS))
    assert any(p.startswith("tool: expected absent") for p in pb.entry_point_problems("main", ep))


def test_a_none_run_has_no_entry_point_and_a_leftover_hook_is_reported(tmp_path):
    clean = pb.entry_points_observed("none", _checkout(tmp_path, hook=False, policy=False), _env(tmp_path), _stream(tmp_path, BASE_TOOLS))
    assert (clean["shell"], clean["hook"], clean["tool"]) == (False, False, False) and pb.entry_point_problems("none", clean) == [], "devkb is denied to it"
    other = tmp_path / "o"
    other.mkdir()
    leftover = pb.entry_points_observed("none", _checkout(other), _env(other), _stream(other, BASE_TOOLS))
    assert any(p.startswith("hook: expected absent") for p in pb.entry_point_problems("none", leftover))


def test_a_hook_switched_off_by_the_environment_does_not_count(tmp_path):
    ep = pb.entry_points_observed("main", _checkout(tmp_path), _env(tmp_path, guardrail="0"), _stream(tmp_path, BASE_TOOLS))
    assert ep["hook"] is False and any(p.startswith("hook: expected present") for p in pb.entry_point_problems("main", ep))


def test_a_stream_with_no_init_event_is_reported_and_an_unlisted_arm_is_not_checked(tmp_path):
    ep = pb.entry_points_observed("main", _checkout(tmp_path), _env(tmp_path), tmp_path / "none.jsonl")
    assert any("no init event" in p for p in pb.entry_point_problems("main", ep))
    assert pb.entry_point_problems("climain", {"shell": False}) == []


def test_the_both_arm_may_use_the_devkb_tools_and_the_none_arm_may_not():
    assert "mcp__devkb" in sb.ALLOW
    assert not any("devkb" in d for d in pb.permissions("both")[1]) and not any("devkb" in d for d in pb.permissions("bothhid")[1])
    assert any("devkb" in d for d in pb.permissions("none")[1])


def test_the_both_arm_writes_the_mcp_server_and_keeps_the_hook(tmp_path, monkeypatch):
    w = _checkout(tmp_path)
    binp = tmp_path / "toolenv" / "bin"
    binp.mkdir(parents=True)
    (binp / "python").write_text("#!/bin/sh\nexit 0\n")
    (binp / "python").chmod(0o755)
    monkeypatch.setattr(pb, "user_mcp", lambda env: '{"mcpServers": {"devkb": {"command": "devkb", "args": ["mcp"]}}}')
    pb.arm_files(w, "both", {"bin": str(binp / "devkb"), "src": str(ROOT)})
    assert json.loads((w / ".mcp.json").read_text())["mcpServers"]["devkb"]["command"] == "devkb"
    assert (w / ".claude" / "settings.json").exists(), "`both` keeps the checkout's hook: the shell entry point stays"
    other = tmp_path / "u"
    other.mkdir()
    w2 = _checkout(other)
    pb.arm_files(w2, "userinit", {"bin": str(binp / "devkb"), "src": str(ROOT)})
    assert not (w2 / ".claude" / "settings.json").exists(), "userinit has the tool without the hook"


def test_a_checkouts_own_suite_does_not_see_the_benchmarks_settings(monkeypatch):
    monkeypatch.setenv("POLICY_ARMS", "both")
    monkeypatch.setenv("POLICY_MAIN", "abc")
    monkeypatch.setenv("KEEP_ME", "1")
    env = pb.suite_env()
    assert "POLICY_ARMS" not in env and "POLICY_MAIN" not in env and env["KEEP_ME"] == "1"
