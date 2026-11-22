"""#391: a search for several names, some of which the graph answers completely, gets those answers beside grep (grep still runs) with the other names
named; never instead of grep."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    d = tmp_path_factory.mktemp("r391") / "r"
    (d / "pkg").mkdir(parents=True)
    (d / "pkg" / "__init__.py").write_text("")
    (d / "pkg" / "a.py").write_text("def only_here(v):\n" + "".join(f"    y{i} = {i}\n" for i in range(12)) + "    return v\n\n\ndef caller():\n    return only_here(1)\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=d, check=True, capture_output=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(d)], cwd=d, env=env, check=True, capture_output=True)
    return d


_n = [0]


def hook(root, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(ROOT), DEVKB_GUARDRAIL_TEACH="0")
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(root), "session_id": f"s391-{_n[0]}", "tool_use_id": f"t391-{_n[0]}"}
    p = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, cwd=ROOT, env=env)
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    log = [json.loads(x) for f in Path(home).rglob("devkb-guardrail.log") for x in f.read_text().splitlines() if x.startswith("{")]
    return out, [r for r in log if r.get("action")][-1:]


def test_a_body_search_for_a_complete_name_and_a_missing_one_gets_the_body_beside_grep(repo, tmp_path):
    out, log = hook(repo, tmp_path, 'grep -n "def only_here\\|def zzmissing" -A3 pkg/a.py')
    text = out.get("additionalContext", "")
    assert "permissionDecision" not in out, "grep still runs"
    assert "y11 = 11" in text and "devkb answers only_here only; grep has zzmissing" in text, text
    assert log[0]["reason"] == "partial:read-body"


def test_an_in_file_search_for_a_complete_name_and_a_missing_one(repo, tmp_path):
    out, log = hook(repo, tmp_path, 'grep -n "only_here\\|zzmissing" pkg/a.py')
    text = out.get("additionalContext", "")
    assert "permissionDecision" not in out
    assert "only_here" in text and "grep has zzmissing" in text, (text, log)


def test_two_names_that_are_both_missing_pass_through(repo, tmp_path):
    out, log = hook(repo, tmp_path, 'grep -n "def zzone\\|def zztwo" -A3 pkg/a.py')
    assert "devkb answers" not in out.get("additionalContext", ""), out
    assert not log or log[0].get("reason") != "partial:read-body", log
