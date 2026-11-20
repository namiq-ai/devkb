"""#375: when grep prints devkb's whole answer itself, the agent is still told which devkb command gives it (once per command
and session, never the answer's lines); a cut-short read names the command for the whole definition; the reminder names the
command form the session has and the MCP tools only when they are configured."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from test_devkb_graph_misses_133 import PRE, ROOT, run

FILES = {
    "pkg/__init__.py": "",
    "pkg/lib.py": "def helper(x):\n    total = x + 1\n    return total\n",
    "pkg/use.py": "from pkg.lib import helper\n\n\ndef go():\n    r = helper(3)\n    return helper(r)\n",
}
TEACH = "Next time ask devkb directly: "


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo375")
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-500:]
    return root


def hook(repo, home, command, session, **extra):
    ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": session, "tool_use_id": f"{session}-{command}",
          "tool_input": {"command": command}}
    out = run(PRE, home, ev, **extra)
    h = json.loads(out)["hookSpecificOutput"] if out.strip() else {}
    return h.get("permissionDecision"), h.get("additionalContext", "")


def spend_reminder(repo, home, session):
    hook(repo, home, 'grep -rn "def nosuchname_z" pkg/', session)


@pytest.mark.parametrize("command,teach", [
    ("grep -n helper pkg/use.py", "devkb uses helper --project ."),                  # duplicate:in-file
    ("grep -rn -A8 helper pkg/", "devkb symbol helper --source --project ."),         # duplicate:read-body
    ("grep -rn helper . && ls", "devkb uses helper --project ."),                     # duplicate:call-sites
])
def test_a_duplicate_answer_adds_only_the_command(repo, tmp_path, command, teach):
    spend_reminder(repo, tmp_path, "s-dup")
    decision, text = hook(repo, tmp_path, command, "s-dup")
    assert decision is None                                    # grep still runs
    assert text == f"{TEACH}`{teach}`"                         # one line; none of the answer's lines


def test_the_command_is_given_once_per_command_and_session(repo, tmp_path):
    spend_reminder(repo, tmp_path, "s-once")
    assert hook(repo, tmp_path, "grep -n helper pkg/use.py", "s-once")[1].startswith(TEACH)
    assert hook(repo, tmp_path, "grep -n helper pkg/use.py", "s-once")[1] == ""
    spend_reminder(repo, tmp_path, "s-other")
    assert hook(repo, tmp_path, "grep -n helper pkg/use.py", "s-other")[1].startswith(TEACH)   # another session: again


def test_teach_off_adds_nothing(repo, tmp_path):
    spend_reminder(repo, tmp_path, "s-off")
    assert hook(repo, tmp_path, "grep -n helper pkg/use.py", "s-off", DEVKB_GUARDRAIL_TEACH="0") == (None, "")


def test_the_reminder_names_no_mcp_tools_and_no_dogfood_log_without_an_mcp_server(repo, tmp_path):
    _, text = hook(repo, tmp_path, 'grep -rn "def nosuchname_y" pkg/', "s-rem")
    assert text.startswith("devkb guardrail:") and "devkb symbol|uses|outline|pack" in text
    assert "mcp__devkb" not in text and "dogfood" not in text


def test_the_reminder_names_the_mcp_tools_when_the_repository_configures_them(repo, tmp_path):
    mcp = repo / ".mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"devkb": {"command": "devkb", "args": ["mcp"]}}}))
    try:
        _, text = hook(repo, tmp_path, 'grep -rn "def nosuchname_x" pkg/', "s-rem-mcp")
    finally:
        mcp.unlink()
    assert "or the mcp__devkb tools" in text


def test_the_reminder_names_the_checkouts_devkb_when_none_is_on_path(repo, tmp_path):
    exe = repo / ".venv" / "bin" / "devkb"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    try:
        _, text = hook(repo, tmp_path, 'grep -rn "def nosuchname_w" pkg/', "s-rem-venv", PATH="/usr/bin:/bin")
    finally:
        exe.unlink()
        exe.parent.rmdir()
        exe.parent.parent.rmdir()
    assert "`.venv/bin/devkb symbol|uses|outline|pack" in text
