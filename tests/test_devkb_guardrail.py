"""#126: the guardrail that reminds a session developing devkb to ask devkb before a text search."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "devkb_guardrail.py"


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    served = tmp_path / "served"
    (served / ".devkb").mkdir(parents=True)
    plain = tmp_path / "plain"
    plain.mkdir()
    return {"home": home, "served": served, "plain": plain}


def hook(env, event: dict, **extra) -> str:
    e = {k: v for k, v in os.environ.items() if k != "DEVKB_GUARDRAIL"}
    e.update(HOME=str(env["home"]), **extra)
    p = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(event), capture_output=True, text=True, env=e,
                       timeout=30)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def bash(cwd, command, n=1):
    return {"tool_name": "Bash", "cwd": str(cwd), "session_id": "s", "tool_use_id": f"t{n}",
            "tool_input": {"command": command}}


def test_a_search_in_a_served_repository_is_reminded_and_logged(env):
    out = hook(env, bash(env["served"], "grep -rn parse src"))
    ctx = json.loads(out)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "PreToolUse" and "ask devkb first" in ctx["additionalContext"]
    log = (env["home"] / ".claude" / "hooks" / "devkb-guardrail.log").read_text().splitlines()
    reminders = [json.loads(x) for x in log if json.loads(x).get("action") == "remind"]   # decisions (#149) are other lines
    assert len(reminders) == 1 and reminders[0]["tool"] == "Bash"


@pytest.mark.parametrize("command", ["git grep -n x", "rg x src", "find . -name '*.py' | xargs grep -l x"])
def test_every_search_form_is_reminded(env, command):
    assert hook(env, bash(env["served"], command))


def test_the_grep_tool_is_reminded(env):
    ev = {"tool_name": "Grep", "cwd": str(env["served"]), "session_id": "s", "tool_use_id": "g1",
          "tool_input": {"pattern": "x"}}
    assert hook(env, ev)


def test_a_search_reached_through_cd_is_reminded(env):
    assert hook(env, bash(env["plain"], f"cd {env['served']} && grep -n x f.py"))


@pytest.mark.parametrize("command", ["pytest -q | grep passed", "ls -la", "git log --oneline | grep fix",
                                     "git commit -m 'reminds at each grep/rg/git grep search'",
                                     'echo "then grep -rn x ."', "cat > f.md <<'EOF'\nuse grep -rn here\nEOF"])
def test_a_filter_or_a_non_search_is_not_reminded(env, command):
    assert hook(env, bash(env["served"], command)) == ""


def test_a_repository_devkb_does_not_serve_is_not_reminded(env):
    assert hook(env, bash(env["plain"], "grep -rn x .")) == ""


def test_the_switch_turns_it_off(env):
    assert hook(env, bash(env["served"], "grep -rn x ."), DEVKB_GUARDRAIL="0") == ""


def test_two_copies_of_the_hook_remind_once(env):
    ev = bash(env["served"], "grep -rn x .", n=7)
    first, second = hook(env, ev), hook(env, ev)
    assert first and second == ""


def test_a_session_is_reminded_once(env):
    assert hook(env, bash(env["served"], "grep -rn x .", n=1))
    assert hook(env, bash(env["served"], "rg y .", n=2)) == "", "a later search in the same session is not reminded"
    other = dict(bash(env["served"], "grep -rn x .", n=3), session_id="s2")
    assert hook(env, other), "another session is reminded"
    log = (env["home"] / ".claude" / "hooks" / "devkb-guardrail.log").read_text().splitlines()
    assert len(log) == 2


def test_the_repository_registers_it():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    cmds = [h["command"] for m in settings["hooks"]["PreToolUse"] if m["matcher"] == "Grep|Bash" for h in m["hooks"]]
    assert any("scripts/devkb_guardrail.py" in c for c in cmds)
    assert "Developing devkb: devkb first, logged" in (ROOT / "AGENTS.md").read_text()
    assert "@AGENTS.md" in (ROOT / "CLAUDE.md").read_text()
    assert not (ROOT / ".mcp.json").exists(), "devkb's own repository uses devkb from the shell (CLI-only, #126)"
