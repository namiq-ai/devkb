"""#166 (SPEC-DKB-006 R1-R3): a definition search is answered with the location and the body in one call."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from pathlib import Path

from test_devkb_graph_misses_133 import ROOT
from test_devkb_guardrail_same_question_162 import decide, sub

BIG = "def big(x):\n" + "".join(f"    x += {i}\n" for i in range(119)) + "    return x\n"
FILES = {
    "pkg/__init__.py": "",
    "pkg/calc.py": "def compute(x):\n    y = x + 1\n    return y\n\n\ndef big_user():\n    return big(1) + compute(2)\n",
    "pkg/big.py": BIG,
    "pkg/one.py": "def dup(x):\n    return x\n",
    "pkg/two.py": "def dup(x):\n    return -x\n",
    "edit/edited.py": "def touched(x):\n    return x\n",   # its own folder: editing it must not make pkg/ stale (#182)
    "pkg/use.py": "from pkg.calc import compute\n\n\ndef go():\n    return compute(3)\n",
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo166")
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


def text(hso):
    return hso.get("permissionDecisionReason", "")


@pytest.mark.parametrize("tool,inp", [("Bash", {"command": 'grep -n "def compute" pkg/'}),
                                      ("Grep", {"pattern": "def compute", "path": "pkg", "output_mode": "content", "-n": True}),
                                      ("Bash", {"command": 'grep -rn "^\\s*compute\\s*(" pkg/'})])
def test_one_definition_gives_the_location_only_280(repo, tmp_path, tool, inp):
    hso, row = decide(repo, tmp_path, tool, inp)
    assert sub(hso) and row["action"] == "read-answer" and row["reason"].startswith("definition")
    t = text(hso)
    assert "pkg/calc.py:1:" in t and "y = x + 1" not in t and "return y" not in t   # #280: locate is grep's one line


def test_long_function_gives_the_location_only_280(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": 'grep -n "def big(" pkg/'})   # bounded: only big itself (#277)
    t = text(hso)
    assert row["action"] == "read-answer" and "pkg/big.py:1:" in t and "x += 100" not in t


def test_a_definition_search_that_also_matches_a_longer_name_is_not_replaced(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": 'grep -n "def big" pkg/'})   # grep also prints def big_user (#277)
    assert row["action"] != "read-answer" and row.get("reason") in ("longer-names", "not-complete") or row["action"] == "pass-through"


def test_several_definitions_give_locations_only(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": 'grep -n "def dup" pkg/'})
    t = text(hso)
    assert row["action"] == "read-answer" and "pkg/one.py:1:" in t and "pkg/two.py:1:" in t
    assert "return -x" not in t and "return x\n" not in t


def test_edited_file_gets_no_answer(repo, tmp_path):
    f = repo / "edit" / "edited.py"
    f.write_text("def touched(x):\n    return x * 2\n")
    future = time.time() + 60
    os.utime(f, (future, future))
    hso, row = decide(repo, tmp_path, "Bash", {"command": 'grep -n "def touched" edit/'})
    assert (row or {}).get("action") != "read-answer" and "return x * 2" not in text(hso)


def test_search_for_uses_is_not_a_read(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": "grep -rn compute pkg/"})
    assert (row or {}).get("action") != "read-answer"



@pytest.mark.parametrize("command", ['grep -n "def compute" -A30 pkg/calc.py', 'grep -n "def compute" -A 30 pkg/calc.py',
                                     'grep -rn "def compute" -C5 pkg/'])
def test_a_definition_search_with_context_lines_is_not_replaced_280(repo, tmp_path, command):
    """#280: grep prints the lines the context options ask for; a replacement that does not carry them is wrong, so it runs."""
    hso, row = decide(repo, tmp_path, "Bash", {"command": command})
    assert not sub(hso) and (row or {}).get("action") != "read-answer"


def test_an_option_value_is_not_a_path_172():
    sys.path.insert(0, str(ROOT / "scripts"))
    import devkb_guardrail as g
    for c in ('grep -n "def compute" -A 30 pkg/calc.py', 'grep -nA 5 compute pkg/calc.py', 'grep -m 3 -n compute pkg/calc.py'):
        paths, _ = g.bash_search(c, Path("/r"))
        assert [p.name for p in paths] == ["calc.py"], c


def test_a_definition_search_with_before_context_is_not_replaced_280(repo, tmp_path):
    hso, row = decide(repo, tmp_path, "Bash", {"command": 'grep -n "def compute" -B3 pkg/calc.py'})
    assert not sub(hso) and (row or {}).get("action") != "read-answer"


def test_a_call_site_search_with_context_is_not_answered_with_the_body_280(repo, tmp_path):
    hso, _ = decide(repo, tmp_path, "Bash", {"command": 'grep -rn "compute(" pkg -A2'})
    assert "y = x + 1" not in hso.get("additionalContext", "") + text(hso)


def test_every_defining_file_gets_its_body_280(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import devkb_guardrail as g
    m = {"k": "pkg/two.py::dup", "ls": 1, "le": 2, "range": "exact", "source": None}
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/two.py").write_text("def dup(x):\n    return -x\n")
    assert g.definition_body(tmp_path, m) == {"lines": ["def dup(x):", "    return -x"]}
