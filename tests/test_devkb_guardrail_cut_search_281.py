"""#281: an answer to a search cut by `| head -N` / `| tail -N` or Grep `head_limit` is never larger than the cut output: the
answer is left out and the search runs."""
import json
import re
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"
sys.path.insert(0, str(ROOT / "scripts"))
import devkb_guardrail as g  # noqa: E402


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r281") / "r"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "a.py").write_text("def helper(x):\n    return x\n\n\n" + "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(4)))
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return root


_n = [0]


def hook(root, home, tool, inp):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(ROOT), DEVKB_GUARDRAIL_TEACH="0")
    ev = {"tool_name": tool, "tool_input": inp, "cwd": str(root), "session_id": f"s281-{_n[0]}", "tool_use_id": f"t281-{_n[0]}"}
    p = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, cwd=root, env=env)
    return json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}


def rows(h):
    """The result lines (`path:line:`) an answer carries."""
    t = (h.get("permissionDecisionReason") or "") + (h.get("additionalContext") or "")
    return sum(1 for ln in t.splitlines() if re.match(r"^\S+\.py:\d+:", ln))


@pytest.mark.parametrize("cmd, n", [("grep -rn helper pkg | head -1", 1), ("grep -rn helper pkg | tail -2", 2),
                                    ("grep -rn helper pkg | head -n 1", 1), ("grep -rn 'def helper' pkg | head -2", 2),
                                    ("grep -rn helper pkg | tail -n +2", 0)])
def test_the_answer_to_a_cut_bash_search_is_not_larger_than_the_cut(repo, tmp_path, cmd, n):
    assert rows(hook(repo, tmp_path, "Bash", {"command": cmd})) <= n


def test_a_grep_tool_head_limit_caps_the_answer(repo, tmp_path):
    inp = {"pattern": "helper", "path": "pkg", "output_mode": "content", "head_limit": 2}
    assert rows(hook(repo, tmp_path, "Grep", inp)) <= 2


def test_an_uncut_search_is_still_answered(repo, tmp_path):
    h = hook(repo, tmp_path, "Bash", {"command": "grep -rn helper pkg"})
    assert rows(h) >= 3


@pytest.mark.parametrize("cmd, limit", [("grep -rn helper pkg | head -3", 3), ("grep -rn helper pkg | tail -n3", 3),
                                        ("grep -rn helper pkg", None), ("grep -rn helper pkg | wc -l", None),
                                        ("grep -rn helper pkg | sort | head -2", 2), ("grep -rn helper pkg | tail -n +2", 0),
                                        ("grep -rn helper pkg | head -5 | tail -2", 2)])
def test_output_limit(cmd, limit):
    assert g.output_limit("Bash", {"command": cmd}) == limit
    assert g.output_limit("Grep", {"head_limit": 4}) == 4 and g.output_limit("Grep", {}) is None
