"""#274: a name with several definitions, or none, does not make the hook pass a search through. Call sites and definitions
of the names devkb has go beside grep, never instead of it; a name devkb has nothing for adds nothing."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"
FILES = {"pkg/__init__.py": "", "pkg/a.py": "def pending(x):\n    return x + 1\n", "pkg/b.py": "def pending(y):\n    return y * 2\n",
         "pkg/lib.py": "def helper(x):\n    total = x + 1\n    return total\n",
         "pkg/use.py": "from pkg.a import pending\nfrom pkg.lib import helper\n\n\ndef go():\n    r = pending(3)\n    return helper(r)\n",
         "pkg/use2.py": "from pkg.b import pending\n\n\ndef go2():\n    return pending(4)\n"}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r274")
    for rel, t in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(t)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return root


_n = [0]


def decide(repo, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(ROOT))
    out = ""
    for j, c in enumerate(("ls", cmd)):
        ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": f"s274-{_n[0]}", "tool_use_id": f"t{_n[0]}-{j}",
              "tool_input": {"command": c}}
        out = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    return json.loads(out).get("hookSpecificOutput", {}) if out.strip() else {}


def test_call_sites_of_an_ambiguous_name_go_beside_grep(repo, tmp_path):
    h = decide(repo, tmp_path, "grep -rn pending pkg/")
    assert h.get("permissionDecision") != "deny"
    ctx = h.get("additionalContext", "")
    assert "pending(3)" in ctx and "pending(4)" in ctx


def test_a_definition_search_for_two_names_lists_every_definition(repo, tmp_path):
    h = decide(repo, tmp_path, "grep -rn 'def pending\\|def helper' pkg/")
    assert h.get("permissionDecision") != "deny"
    ctx = h.get("additionalContext", "")
    assert "pkg/a.py" in ctx and "pkg/b.py" in ctx and "def helper" in ctx


def test_an_unknown_name_does_not_block_the_others_and_adds_nothing(repo, tmp_path):
    h = decide(repo, tmp_path, "grep -rn 'def helper\\|def nosuchname' pkg/")
    ctx = h.get("additionalContext", "") or h.get("permissionDecisionReason", "")
    assert "def helper" in ctx and "nosuchname" not in ctx.replace("def nosuchname", "")
