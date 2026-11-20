"""#167 (SPEC-DKB-006 R4-R6): a read that stops partway through a function gets a one-line span hint."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from test_devkb_graph_misses_133 import PRE, ROOT, run
from test_devkb_guardrail_same_question_162 import decide

BODY = "def pure_search(x):\n" + "".join(f"    x += {i}\n" for i in range(6)) + "    return x\n"
FILES = {"pkg/__init__.py": "", "pkg/mod.py": "import os\n\n\n" + BODY,
         "pkg/edited.py": "def h():\n    a = 1\n    b = 2\n    return a + b\n", "notes.txt": "a\nb\nc\nd\n"}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo167")
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


def ctx(hso):
    return hso.get("additionalContext", "")


# pure_search runs L4-L11 in pkg/mod.py
@pytest.mark.parametrize("tool,inp,stop", [("Bash", {"command": "sed -n 4,7p pkg/mod.py"}, 7),
                                           ("Bash", {"command": "sed -n '5,8p' pkg/mod.py"}, 8),
                                           ("Read", {"file_path": "pkg/mod.py", "offset": 4, "limit": 4}, 7),
                                           ("Bash", {"command": "sed -n 4,10p pkg/mod.py"}, 10)])
def test_cut_short_range_gets_hint(repo, tmp_path, tool, inp, stop):
    hso, row = decide(repo, tmp_path, tool, inp)
    assert ctx(hso) == (f"this range stops at L{stop}; pure_search runs L4–L11\n"
                        "Next time ask devkb directly: `devkb symbol pure_search --source --project .`")   # #375
    assert hso.get("permissionDecision") is None
    assert row["action"] == "span-hint"


@pytest.mark.parametrize("tool,inp", [("Bash", {"command": "sed -n 4,11p pkg/mod.py"}),
                                      ("Bash", {"command": "sed -n 1,20p pkg/mod.py"}),
                                      ("Read", {"file_path": "pkg/mod.py", "offset": 4, "limit": 50}),
                                      ("Read", {"file_path": "pkg/mod.py"}),
                                      ("Bash", {"command": "sed -n 1,2p pkg/mod.py"}),
                                      ("Bash", {"command": "tail -n +5 pkg/mod.py"}),
                                      ("Bash", {"command": "sed -n 2,3p notes.txt"})])
def test_covering_or_non_code_gets_none(repo, tmp_path, tool, inp):
    hso, _ = decide(repo, tmp_path, tool, inp)
    assert ctx(hso) == ""


def test_stale_file_gets_none(repo, tmp_path):
    f = repo / "pkg" / "edited.py"
    future = time.time() + 100
    f.write_text(f.read_text() + "\n")
    os.utime(f, (future, future))
    hso, _ = decide(repo, tmp_path, "Bash", {"command": "sed -n 1,2p pkg/edited.py"})
    assert ctx(hso) == ""


def test_once_per_range_per_session(repo, tmp_path):
    ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": "s167-once",
          "tool_input": {"command": "sed -n 4,6p pkg/mod.py"}}
    first = run(PRE, tmp_path, dict(ev, tool_use_id="a"))
    second = run(PRE, tmp_path, dict(ev, tool_use_id="b"))
    assert "this range stops" in first and second.strip() == ""
