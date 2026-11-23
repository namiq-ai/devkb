"""#366: the user-facing arms hold what `devkb init` writes (or the short candidate), and the inject arm puts the pack of
the ticket's code file in front of the prompt."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
sys.path.insert(0, str(ROOT))
import policybench as pb  # noqa: E402
import release_table as rt  # noqa: E402
from devkb import init  # noqa: E402


def test_userpolicy_is_what_devkb_init_writes(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    init.run(tmp_path, "cli", hooks=False, dry_run=False)
    agents, claude = pb.user_policy({"src": str(ROOT)}, "full")
    assert agents == (tmp_path / "AGENTS.md").read_text()
    assert claude == (tmp_path / "CLAUDE.md").read_text()
    assert "Developing devkb" not in agents                 # this repository's own process text is not a user's


def test_short_is_shorter_and_names_the_commands():
    full, _ = pb.user_policy({"src": str(ROOT)}, "full")
    short, claude = pb.user_policy({"src": str(ROOT)}, "short")
    assert len(short) < len(full) / 3 and claude.strip().splitlines()[1] == "@AGENTS.md"
    assert all(c in short for c in ("devkb symbol", "devkb uses", "devkb pack --project . file", "refactor"))


def test_the_arms_run_mains_devkb_and_are_in_the_table():
    for a in ("userpolicy", "short", "inject"):
        assert a in pb.BASES and a in pb.ENV_REF and pb.ARM_ENV[a] == pb.ARM_ENV["main"] and a in pb.USER_POLICY
        assert a in rt.ORDER and a not in rt.NONE


def test_write_user_policy_replaces_the_checkouts_files(tmp_path):
    (tmp_path / "AGENTS.md").write_text("## Developing devkb\nprocess\n")
    pb.write_user_policy(tmp_path, {"src": str(ROOT)}, "short")
    assert (tmp_path / "AGENTS.md").read_text() == pb.user_policy({"src": str(ROOT)}, "short")[0]


def test_inject_gives_the_pack_of_the_file_where_to_start_names_first(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pkg" / "core.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "a_much_longer_module_name.py").write_text("x = 1\n")
    (tmp_path / "tests" / "test_core.py").write_text("x = 1\n")
    body = ("**Scope:** `pkg/a_much_longer_module_name.py`, `pkg/core.py`.\n\n"
            "**Where to start:** `tests/test_core.py` and `core.main`, then `pkg/a_much_longer_module_name.py`.\n")
    monkeypatch.setattr(pb, "ticket_for", lambda issue: {"title": "t", "body": body})
    fake = tmp_path / "devkb"
    fake.write_text("#!/bin/sh\necho \"PACK $*\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    text = pb.injected_context("1", tmp_path, str(fake))
    assert text.startswith("Before this session, devkb ran `devkb pack --project . file pkg/core.py`")
    assert "PACK pack --project . file pkg/core.py" in text      # the checkout's path shown as `.`
    assert pb.start_files(body, tmp_path) == ["pkg/core.py", "pkg/a_much_longer_module_name.py"]  # its order, code first
    scope_only = "**Scope:** `pkg/a_much_longer_module_name.py`.\n\n**Where to start:** the parser.\n"
    assert pb.start_files(scope_only, tmp_path) == ["pkg/a_much_longer_module_name.py"]
    monkeypatch.setattr(pb, "ticket_for", lambda issue: {"title": "t", "body": "No location."})
    assert pb.injected_context("1", tmp_path, str(fake)) == ""


def test_the_checkout_of_a_user_arm_holds_the_user_policy(tmp_path):
    for arm, kind in (("userpolicy", "full"), ("short", "short"), ("inject", "full"), ("main", None)):
        w = tmp_path / arm
        w.mkdir()
        (w / "AGENTS.md").write_text("## Developing devkb\nprocess\n")
        pb.arm_files(w, arm, {"src": str(ROOT)})              # what checkout() calls for every arm
        got = (w / "AGENTS.md").read_text()
        assert got == (pb.user_policy({"src": str(ROOT)}, kind)[0] if kind else "## Developing devkb\nprocess\n"), arm
    src = (ROOT / "bench" / "policy" / "policybench.py").read_text()
    body = src[src.index("def checkout("):src.index("\ndef ", src.index("def checkout(") + 5)]
    assert "arm_files(w, arm, env)" in body


def test_userinit_holds_everything_a_default_devkb_init_writes_and_no_guardrail(tmp_path):
    import json
    w = tmp_path / "w"
    (w / ".claude").mkdir(parents=True)
    (w / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": []}}')
    (w / "AGENTS.md").write_text("## Developing devkb\n")
    fake = tmp_path / "env" / "bin"                    # a tool environment whose python already has `mcp`: nothing installed
    fake.mkdir(parents=True)
    (fake / "python").write_text("#!/bin/sh\nexit 0\n")
    (fake / "python").chmod(0o755)
    pb.arm_files(w, "userinit", {"src": str(ROOT), "bin": str(fake / "devkb")})
    assert (w / "AGENTS.md").read_text() == pb.user_policy({"src": str(ROOT)}, "full")[0]
    server = json.loads((w / ".mcp.json").read_text())["mcpServers"]["devkb"]
    assert server["args"][-2:] == ["--toolset", pb.USER_INIT] and pb.USER_INIT == "lean-pack"
    assert not (w / ".claude" / "settings.json").exists()              # init installs no hook without --claude-hook
    assert "userinit" in rt.ORDER and pb.ENV_REF["userinit"] and "userinit" in pb.USER_POLICY


def test_userinit_gets_no_guardrail_hook_and_runs_its_committed_mcp_config():
    src = (ROOT / "bench" / "policy" / "policybench.py").read_text()
    co = src[src.index("def checkout("):src.index("\ndef ", src.index("def checkout(") + 5)]
    assert 'if env and arm != "userinit":' in co                         # the hook step skips userinit
    run = src[src.index("def _run_one"):src.index("\ndef ", src.index("def _run_one") + 5)]
    head = 'if arm in ("userinit", "both", "bothuser"):'                              # `both` reads the same committed MCP config (the tool entry point)
    branch = run[run.index(head):run.index("elif", run.index(head))]
    assert 'mcp = str(w / ".mcp.json")' in branch and "write_text" not in branch   # the checkout's file, unchanged
