"""#282: a listing of one kind of definition gets only that kind within grep's size; a keyword searched as text gets nothing; a language-specific
pattern lists only that language's definitions."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("devkb_guardrail", ROOT / "scripts" / "devkb_guardrail.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

PY = ("class A:\n    def m1(self):\n        return 1\n\n    def m2(self):\n        return 2\n\n\nclass B:\n    X = 1\n\n    def m3(self):\n        return 3\n\n\n"
      "def top1():\n    return 1\n\n\nCONST = 5\n\n\ndef top2():\n    return 2\n")
JS = "function alpha() {\n  return 1;\n}\n\nclass Widget {\n  render() {\n    return 2;\n  }\n}\n"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r282")
    (root / "m.py").write_text(PY)
    (root / "w.js").write_text(JS)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


def names(ans):
    return [ln.split(" ", 2)[1:] for ln in (ans or "").splitlines()]


def test_a_class_listing_gets_only_the_classes(repo):
    got = g.outline_answer(repo, [repo / "m.py"], "^class ")
    assert [n[1] for n in names(got)] == ["A", "B"], got                      # grep prints 2 lines; so does the answer


def test_a_top_level_def_listing_gets_only_top_level_functions(repo):
    got = g.outline_answer(repo, [repo / "m.py"], "^def ")
    assert [n[1] for n in names(got)] == ["top1", "top2"], got


def test_an_indented_def_listing_adds_the_methods_but_not_classes_or_constants(repo):
    got = g.outline_answer(repo, [repo / "m.py"], "    def ")
    assert sorted(n[1] for n in names(got)) == ["A.m1", "A.m2", "B.m3", "top1", "top2"], got


def test_a_def_pattern_over_a_javascript_file_lists_nothing(repo):
    assert g.outline_answer(repo, [repo / "w.js"], "^def ") is None
    assert g.outline_answer(repo, [repo / "m.py"], "^function ") is None                # the keyword of another language
    assert g.outline_answer(repo, [repo / "w.js"], "^function ") is not None


def test_a_listing_with_no_pattern_still_returns_the_whole_outline(repo):
    assert len(names(g.outline_answer(repo, [repo / "m.py"]))) >= 8                     # the first-open outline is unchanged


@pytest.mark.parametrize("cmd", ["grep -n async m.py", "grep -n static m.py", "grep -rn async .", "grep -n '\\bclass\\b' m.py"])
def test_a_keyword_searched_as_text_is_not_a_definition_listing(repo, cmd):
    pat, why = g.bash_pattern(cmd), g.bash_search(cmd, repo)
    assert g.classify("Bash", {"command": cmd}, pat, why[1], why[0]) != "list-symbols", cmd


@pytest.mark.parametrize("cmd", ["grep -n '^def ' m.py", "grep -n '^class ' m.py", "grep -n '    def ' m.py", "grep -n 'def ' m.py",
                                 "grep -n '    def \\|^class ' m.py"])
def test_a_real_definition_listing_still_is(repo, cmd):
    pat, why = g.bash_pattern(cmd), g.bash_search(cmd, repo)
    assert g.classify("Bash", {"command": cmd}, pat, why[1], why[0]) == "list-symbols", cmd
