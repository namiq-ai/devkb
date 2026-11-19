"""#175: a search for a string key the graph records gets the key's writes and reads by function beside grep, inside
the searched scope; a name that is neither a symbol nor a key still passes through."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"
REPORT = ('def collect(files):\n    out = {"unresolved_files": [], "seen": 0}\n    for f in files:\n'
          '        out["unresolved_files"].append(f)\n    return out\n\n\n'
          'def show(r):\n    # nothing_here\n    return len(r["unresolved_files"])\n')


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r175")
    (root / "pkg").mkdir()
    (root / "tests").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "report.py").write_text(REPORT)
    (root / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env,
                   check=True, capture_output=True)
    return root


_n = [0]


def hook(repo, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env["HOME"] = str(home)
    out = ""
    for j, c in enumerate(("ls", "grep -rn zz_warmup .", cmd)):
        ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": f"s175-{_n[0]}", "tool_use_id": f"t{_n[0]}-{j}",
              "tool_input": {"command": c}}
        out = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    h = json.loads(out)["hookSpecificOutput"] if out.strip() else {}
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"
    rows = [json.loads(l) for l in log.read_text().splitlines() if f'"s175-{_n[0]}"' in l and '"remind"' not in l]
    text = h.get("additionalContext", "")
    return ("" if "devkb guardrail: this is a code search" in text else text), h.get("permissionDecision"), rows[-1] if rows else {}


def test_a_key_search_gets_its_writes_and_reads_by_function_alongside(repo, tmp_path):
    text, decision, row = hook(repo, tmp_path, "grep -rn unresolved_files pkg/")
    assert decision is None and "pkg/report.py  collect  writes L2; reads L4" in text and "pkg/report.py  show  reads L10" in text
    assert row["action"] == "alongside" and row["reason"] == "key"


def test_a_key_in_one_file_is_answered_for_that_file(repo, tmp_path):
    text, _, row = hook(repo, tmp_path, "grep -n seen pkg/report.py")
    assert "collect  writes L2" in text and row["reason"] == "key"


def test_a_key_outside_the_searched_folder_and_a_name_that_is_nothing_pass_through(repo, tmp_path):
    for cmd in ("grep -rn unresolved_files tests/", "grep -rn nothing_here pkg/"):
        text, decision, row = hook(repo, tmp_path, cmd)
        assert text == "" and decision is None and row["action"] == "pass-through"
