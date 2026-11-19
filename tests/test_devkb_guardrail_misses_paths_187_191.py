"""#187: a definition search devkb cannot answer still records its miss and logs the real reason. #191: answers show
paths as grep prints them from the search's directory."""
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
    root = tmp_path_factory.mktemp("r187")
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text("def compute(x):\n    return x * 2\n")
    (root / "pkg" / "app.py").write_text("from pkg.core import compute\n\n\ndef run():\n    return compute(3)\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return root


_n = [0]


def hook(cwd, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env["HOME"] = str(home)
    out = ""
    for j, c in enumerate(("ls", cmd)):
        ev = {"tool_name": "Bash", "cwd": str(cwd), "session_id": f"s187-{_n[0]}", "tool_use_id": f"t{_n[0]}-{j}",
              "tool_input": {"command": c}}
        out = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    h = json.loads(out)["hookSpecificOutput"] if out.strip() else {}
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"
    rows = [json.loads(l) for l in log.read_text().splitlines() if f'"s187-{_n[0]}"' in l and '"remind"' not in l]
    return h.get("permissionDecisionReason", "") + h.get("additionalContext", ""), rows[-1] if rows else {}, f"t{_n[0]}-1"


def test_an_unanswerable_definition_search_records_its_miss_with_the_real_reason(repo, tmp_path):
    _text, row, key = hook(repo, tmp_path, 'grep -n "def nothere" -A5 pkg/core.py')
    assert row["action"] == "pass-through" and row["reason"].startswith("verdict:")
    assert (tmp_path / ".claude" / "hooks" / ".devkb-guardrail-pending" / key).exists()


def test_a_definition_answer_from_a_subfolder_shows_the_path_grep_prints(repo, tmp_path):
    text, row, _ = hook(repo / "pkg", tmp_path, 'grep -n "def compute" core.py')
    assert row["action"] == "read-answer" and "\ncore.py:1:def compute" in text and "pkg/core.py:1:" not in text


def test_cd_then_search_shows_paths_from_that_folder(repo, tmp_path):
    text, row, _ = hook(repo, tmp_path, 'cd pkg && grep -rn compute .')
    assert row["action"] == "substitute" and "app.py:5:" in text and "pkg/app.py" not in text
