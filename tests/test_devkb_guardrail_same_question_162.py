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


@pytest.mark.parametrize("command", ["grep -rn extract pkg/ scripts/", "grep -rnwE extract --color=auto pkg/ scripts/",
                                     "grep -rn extract pkg/ scripts/ | head -5", "grep -rn extract pkg/ scripts/ | tail -3"])
def test_same_question_is_substituted(repo, tmp_path, command):
    hso, row = decide(repo, tmp_path, "Bash", {"command": command})
    assert sub(hso) and row["action"] == "substitute" and row["reason"] == "same-question"


@pytest.mark.parametrize("command", ["grep -rn extract .", "grep -rn extract", "grep -rnwE extract --color=auto .",
                                     "grep -rn extract . | head", "grep -rn extract . | head -n 20 | tail -n5",
                                     "grep -rn extract . | tail -n +2", "grep -rn extract . | head --lines=8"])
def test_a_search_that_reaches_a_doc_mentioning_the_name_is_not_replaced(repo, tmp_path, command):
    hso, row = decide(repo, tmp_path, "Bash", {"command": command})   # docs/readme.md mentions extract: grep prints it (#276)
    assert not sub(hso) and row["reason"] == "non-code-path"


def test_folder_narrows_the_answer(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": "grep -rn extract tests/"})
    text = hso["permissionDecisionReason"]
    assert sub(hso) and "tests/test_alpha.py:" in text                  # grep-like lines, from tests/ only (SPEC-DKB-007)
    assert "scripts/tool.py" not in text and "pkg/use.py" not in text
    assert row["scope"] == ["tests"]


def test_nothing_in_scope_passes_through(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": "grep -rn extract docs/"})
    assert not sub(hso) and row["action"] == "pass-through" and row["reason"] == "nothing-in-scope"


@pytest.mark.parametrize("command,reason", [
    ("grep -rn extract . | grep -v test", "duplicate:call-sites-filtered"),
    ("grep -rn extract . | sort", "duplicate:call-sites"),
    ("grep -rn extract . | head -c 200", "duplicate:call-sites"),
    ("grep -rn extract . | tail -f", "duplicate:call-sites"),
    ("grep -rn extract . | sort | head -5", "duplicate:call-sites"),
    ("grep -rn -A8 extract .", "duplicate:read-body"),   # -A8 already shows extract's whole body
    ("grep -n extract pkg/use.py", "duplicate:in-file"),
    ("grep -rn extract . && ls", "duplicate:call-sites"),
])
def test_lines_grep_prints_anyway_are_not_added_beside_it(repo, tmp_path, command, reason):
    """SPEC-DKB-007 R5 (#217): grep runs and prints these lines; the same lines beside them would only cost tokens. What is
    added, if anything, is the one line naming the devkb command that answers the search (#375), never a line of the answer."""
    hso, row = decide(repo, tmp_path, "Bash", {"command": command})
    answer = hso.get("permissionDecisionReason", "") + hso.get("additionalContext", "")
    assert not sub(hso)
    assert (not answer or answer.startswith("devkb guardrail: this is a code search")
            or (answer.startswith("Next time ask devkb directly: `devkb ") and "\n" not in answer.strip() and ".py:" not in answer))
    assert row["action"] == "teach" and row["reason"] == reason   # #375: the command, logged as its own decision


@pytest.mark.parametrize("command,intent", [
    ("grep -rn extract . | wc -l", "count"), ("grep -rn extract . | head -5 | wc -l", "count"),
    ("grep -rc extract .", "count"), ("grep -rl extract .", "list-files"), ("grep -rnv extract pkg/use.py", "invert"),
])
def test_counts_file_lists_and_inverted_searches_get_no_answer(repo, tmp_path, command, intent):
    hso, row = decide(repo, tmp_path, "Bash", {"command": command})
    answer = hso.get("permissionDecisionReason", "") + hso.get("additionalContext", "")
    assert not sub(hso) and (not answer or answer.startswith("devkb guardrail: this is a code search"))  # at most the reminder
    assert row["action"] == "pass-through" and row["reason"] == f"intent:{intent}"


@pytest.mark.parametrize("inp,action,reason", [
    ({"pattern": "extract", "output_mode": "count"}, "pass-through", "intent:count"),
    ({"pattern": "extract", "output_mode": "content", "-i": True}, "teach", "duplicate:call-sites"),
    ({"pattern": "extract", "output_mode": "content", "-C": 5}, "teach", "duplicate:read-body"),
    ({"pattern": "extract", "output_mode": "content", "multiline": True}, "pass-through", "intent:unknown"),
    ({"pattern": "extract"}, "pass-through", "intent:list-files"),   # the default output_mode: a file list
    ({"pattern": "extract", "output_mode": "content", "path": "pkg/use.py"}, "teach", "duplicate:in-file"),
])
def test_grep_tool_variants(repo, tmp_path, inp, action, reason):
    hso, row = decide(repo, tmp_path, "Grep", inp)
    assert not sub(hso) and row["action"] == action and row["reason"] == reason


def test_grep_tool_plain_and_scoped(repo, tmp_path):
    assert not sub(decide(repo, tmp_path, "Grep", {"pattern": "extract", "output_mode": "content"})[0])   # reaches docs (#276)
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
