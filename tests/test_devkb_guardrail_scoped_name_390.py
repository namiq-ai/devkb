"""#390: a name several symbols share, searched in files that hold exactly one definition of it, is resolved there and answered; several definitions in
the searched files, or a repository-wide search, pass through as before."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"
sys.path.insert(0, str(ROOT / "scripts"))
import devkb_guardrail as g  # noqa: E402

BODY = "".join(f"    x{i} = {i}\n" for i in range(30))


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r390") / "r"
    (root / "pkg").mkdir(parents=True)
    (root / "other").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "a.py").write_text("def shared(v):\n" + BODY + "    return v\n")
    (root / "pkg" / "b.py").write_text("def shared(v):\n    return v + 1\n\n\ndef uses_it():\n    return shared(2)\n")
    (root / "other" / "c.py").write_text("def shared(v):\n    return v + 2\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True, capture_output=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


_n = [0]


def hook(root, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(ROOT), DEVKB_GUARDRAIL_TEACH="0")
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(root), "session_id": f"s390-{_n[0]}", "tool_use_id": f"t390-{_n[0]}"}
    p = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, cwd=root, env=env)
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    return (out.get("permissionDecisionReason") or "") + (out.get("additionalContext") or "")


def test_a_shared_name_with_one_definition_in_the_searched_file_gets_its_body(repo, tmp_path):
    t = hook(repo, tmp_path, 'grep -n "def shared" -A5 pkg/a.py')
    assert "devkb, from the graph" in t and "x29 = 29" in t, t       # the body beyond grep's 5 lines of context


def test_several_definitions_in_the_searched_files_pass_through(repo, tmp_path):
    t = hook(repo, tmp_path, 'grep -n "def shared" -A5 pkg/a.py pkg/b.py')
    assert "x29 = 29" not in t


def test_a_repository_wide_search_of_a_shared_name_passes_through(repo, tmp_path):
    assert "x29 = 29" not in hook(repo, tmp_path, 'grep -rn "def shared" -A5 .')


def test_a_body_that_grep_prints_in_full_is_not_repeated(repo, tmp_path):
    assert "x29 = 29" not in hook(repo, tmp_path, 'grep -n "def shared" -A60 pkg/a.py')


def test_the_scoped_check_itself(repo):
    assert g.scoped_unique_definition(repo, "shared", ["pkg/a.py"], None) is True
    assert g.scoped_unique_definition(repo, "shared", ["pkg"], None) is False        # a.py and b.py
    assert g.scoped_unique_definition(repo, "shared", None, None) is False           # repository-wide
    assert g.scoped_unique_definition(repo, "shared", None, ["a.py"]) is True        # --include=a.py
