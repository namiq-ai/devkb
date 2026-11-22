"""#358: a definition search with context options is not replaced, and carries the pointer to `devkb symbol NAME --source` once per session; DEVKB_GUARDRAIL_TEACH=0 and
DEVKB_GUARDRAIL_TEACH_BODY=0 silence it."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CMD = 'grep -n "def compute" -A20 pkg/core.py'


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r358")
    (root / "pkg").mkdir()
    (root / "pkg" / "core.py").write_text("def compute(x):\n    return x * 2\n\n\ndef other():\n    return compute(3)\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


def hook(repo, home, cmd=CMD, session="s9", **env):
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(repo), "session_id": session}
    e = {**os.environ, "HOME": str(home), "PYTHONPATH": str(ROOT), **env}
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "devkb_guardrail.py")], input=json.dumps(ev), capture_output=True, text=True, env=e)
    return json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else None


def pointers(out):
    return "devkb symbol compute --source" in (out or {}).get("additionalContext", "")


def test_the_search_is_not_replaced_and_carries_the_pointer(repo, tmp_path):
    out = hook(repo, tmp_path)
    assert pointers(out) and "permissionDecision" not in out, out


def test_the_pointer_is_given_once_per_command_and_session(repo, tmp_path):
    assert pointers(hook(repo, tmp_path))
    again = hook(repo, tmp_path)
    assert not pointers(again), again
    assert pointers(hook(repo, tmp_path, session="another")), "a new session is told again"


def test_teach_off_silences_it(repo, tmp_path):
    assert not pointers(hook(repo, tmp_path, DEVKB_GUARDRAIL_TEACH="0"))


def test_its_own_switch_silences_it_without_touching_the_other_teach_lines(repo, tmp_path):
    assert not pointers(hook(repo, tmp_path, DEVKB_GUARDRAIL_TEACH_BODY="0"))


def test_a_name_the_graph_cannot_answer_gets_no_pointer(repo, tmp_path):
    out = hook(repo, tmp_path, cmd='grep -n "def no_such_function" -A20 pkg/core.py')
    assert not pointers(out) and "symbol no_such_function" not in json.dumps(out), out
