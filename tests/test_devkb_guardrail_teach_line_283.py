"""#283: the teach line's command runs as written in the directory the search ran in, names the answer it follows,
and quotes what needs quoting."""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"
FILES = {"pkg/__init__.py": "", "pkg/a.py": "def helper(x):\n    return x\n\n\ndef run():\n    return helper(0) + helper(1)\n",
         "pkg/m.py": "def go(d):\n    d[\"beta_key\"] = 1\n    return d[\"beta_key\"]\n",
         "my dir/with space.py": "def spaced_fn():\n    return 1\n"}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r283")
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


def teach(cwd, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(ROOT))
    out = ""
    for j, c in enumerate(("ls", cmd)):
        ev = {"tool_name": "Bash", "cwd": str(cwd), "session_id": f"s283-{_n[0]}", "tool_use_id": f"t{_n[0]}-{j}",
              "tool_input": {"command": c}}
        out = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    h = json.loads(out).get("hookSpecificOutput", {}) if out.strip() else {}
    text = h.get("permissionDecisionReason", "") + h.get("additionalContext", "")
    line = next((l for l in text.splitlines() if l.startswith("Next time ask devkb directly:")), "")
    return line.split("`")[1] if "`" in line else ""


def runs(cmd, cwd):
    w = shlex.split(cmd)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", *w[1:]], cwd=cwd, env=env, capture_output=True, text=True)
    return p.returncode == 0 and "no devkb graph" not in (p.stdout + p.stderr)


def test_the_command_runs_from_the_subfolder_the_search_ran_in(repo, tmp_path):
    cmd = teach(repo / "pkg", tmp_path, "grep -rn helper .")
    assert cmd and "--project .." in cmd and runs(cmd, repo / "pkg"), cmd


def test_the_command_names_the_key_it_answered(repo, tmp_path):
    cmd = teach(repo, tmp_path, "grep -rn beta_key pkg/")
    assert "beta_key" in cmd and runs(cmd, repo), cmd


def test_a_path_with_a_space_is_quoted(repo, tmp_path):
    cmd = teach(repo, tmp_path, 'grep -n "^def " "my dir/with space.py"')
    assert "'my dir/with space.py'" in cmd and runs(cmd, repo), cmd
