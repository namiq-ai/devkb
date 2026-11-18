"""#162: the guardrail replaces a search only when devkb's pack answers the same question (folder, flags, pipes, repo)."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from test_devkb_graph_misses_133 import PRE, ROOT, run

FILES = {
    "pkg/__init__.py": "",
    "pkg/alpha.py": "def extract(x):\n    return x\n",
    "pkg/use.py": "from pkg import alpha\n\n\ndef go():\n    return alpha.extract(1)\n",
    "scripts/tool.py": "from pkg import alpha\n\n\ndef tool():\n    return alpha.extract(2)\n",
    "tests/test_alpha.py": "from pkg import alpha\n\n\ndef test_a():\n    assert alpha.extract(3)\n",
    "docs/readme.md": "extract is documented here\n",
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo162")
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


_n = [0]


def decide(repo, home, tool, inp):
    """(hook output, the guardrail-log row this call wrote or None)."""
    _n[0] += 1
    ev = {"tool_name": tool, "cwd": str(repo), "session_id": f"s162-{_n[0]}", "tool_use_id": f"t162-{_n[0]}",
          "tool_input": inp}
    out = run(PRE, home, ev)
    hso = json.loads(out)["hookSpecificOutput"] if out.strip() else {}
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"
    rows = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    return hso, next((r for r in reversed(rows) if r["session"] == ev["session_id"] and r["action"] != "remind"), None)


def sub(hso):
    return hso.get("permissionDecision") == "deny"


@pytest.mark.parametrize("command", ["grep -rn extract .", "grep -rn extract", "grep -rn extract pkg/ scripts/",
                                     "grep -rnwE extract --color=auto ."])
def test_same_question_is_substituted(repo, tmp_path, command):
    hso, row = decide(repo, tmp_path, "Bash", {"command": command})
    assert sub(hso) and row["action"] == "substitute" and row["reason"] == "same-question"


def test_folder_narrows_the_answer(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": "grep -rn extract tests/"})
    text = hso["permissionDecisionReason"]
    assert sub(hso) and "Filtered to tests/" in text
    assert "tests/test_alpha.py" in text and "scripts/tool.py" not in text and "pkg/use.py" not in text
    assert row["scope"] == ["tests"]


def test_nothing_in_scope_passes_through(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": "grep -rn extract docs/"})
    assert not sub(hso) and row["action"] == "pass-through" and row["reason"] == "nothing-in-scope"


@pytest.mark.parametrize("command,reason", [
    ("grep -rn extract . | wc -l", "pipe"),
    ("grep -rn extract . | grep -v test", "pipe"),
    ("grep -rc extract .", "option:-c"),
    ("grep -rl extract .", "option:-l"),
    ("grep -rnv extract pkg/use.py", "option:-v"),
    ("grep -n -A8 'def extract' pkg/alpha.py", "option:-A"),
    ("grep -n extract pkg/use.py", "file-operand"),
    ("grep -rn extract . && ls", "compound"),
])
def test_other_questions_get_the_answer_alongside(repo, tmp_path, command, reason):
    hso, row = decide(repo, tmp_path, "Bash", {"command": command})
    assert not sub(hso) and "additionalContext" in hso
    assert row["action"] == "alongside" and row["reason"] == reason


@pytest.mark.parametrize("inp,reason", [
    ({"pattern": "extract", "output_mode": "count"}, "output_mode:count"),
    ({"pattern": "extract", "output_mode": "content", "-i": True}, "option:-i"),
    ({"pattern": "extract", "output_mode": "content", "-C": 5}, "context"),
    ({"pattern": "extract", "output_mode": "content", "multiline": True}, "multiline"),
    ({"pattern": "extract"}, "option:files"),                       # the default output_mode: a file list
    ({"pattern": "extract", "output_mode": "content", "path": "pkg/use.py"}, "file-operand"),
])
def test_grep_tool_variants_are_alongside(repo, tmp_path, inp, reason):
    hso, row = decide(repo, tmp_path, "Grep", inp)
    assert not sub(hso) and row["action"] == "alongside" and row["reason"] == reason


def test_grep_tool_plain_and_scoped(repo, tmp_path):
    assert sub(decide(repo, tmp_path, "Grep", {"pattern": "extract", "output_mode": "content"})[0])
    hso, _ = decide(repo, tmp_path, "Grep", {"pattern": "extract", "path": str(repo / "scripts"), "output_mode": "content"})
    text = hso["permissionDecisionReason"]
    assert sub(hso) and "scripts/tool.py" in text and "tests/test_alpha.py" not in text


@pytest.mark.parametrize("tool,inp", [
    ("Bash", {"command": "grep -rn extract . --include=*.md"}),
    ("Grep", {"pattern": "extract", "glob": "*.md", "output_mode": "content"}),
])
def test_a_document_only_search_gets_no_devkb_text(repo, tmp_path, tool, inp):
    hso, row = decide(repo, tmp_path, tool, inp)
    assert not sub(hso) and "resolved" not in hso.get("additionalContext", "")
    assert row["action"] == "pass-through" and row["reason"] == "document-glob"


def test_a_leading_cd_only_sets_the_directory(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": "cd scripts && grep -rn extract ."})
    assert sub(hso) and row["reason"] == "same-question" and "tests/test_alpha.py" not in hso["permissionDecisionReason"]


def test_other_repository_passes_through(repo, tmp_path):
    other = tmp_path / "another-repo"
    other.mkdir()
    (other / "a.py").write_text("extract = 1\n")
    assert decide(repo, tmp_path, "Bash", {"command": f"grep -rn extract {other}"})[0] == {}
    assert decide(repo, tmp_path, "Bash", {"command": f"grep -rn extract {repo} {other}"})[0] == {}
