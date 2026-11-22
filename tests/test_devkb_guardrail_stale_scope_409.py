"""#409: a graph that has not seen some changed files still answers a search for names that no changed file mentions, when the answer cites no changed
file. Each case runs the real hook on a built repository."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"
sys.path.insert(0, str(ROOT / "scripts"))
import devkb_guardrail as g  # noqa: E402

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
SEARCH = {"command": "grep -rn helper ."}


def git(cwd, *a):
    return subprocess.run([*GIT, *a], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("r409") / "r"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "a.py").write_text("def helper(x):\n    return x\n\n\n" + "".join(f"def f{i}():\n    return helper({i})\n\n\n" for i in range(4)))
    (root / "pkg" / "b.py").write_text("def other():\n    return 1\n")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-qm", "x")
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


@pytest.fixture
def repo(built, tmp_path):
    w = tmp_path / "w"
    shutil.copytree(built, w)
    return w


_n = [0]


def hook(root, home, inp=SEARCH):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(ROOT), DEVKB_GUARDRAIL_TEACH="0")
    ev = {"tool_name": "Bash", "tool_input": inp, "cwd": str(root), "session_id": f"s409-{_n[0]}", "tool_use_id": f"t409-{_n[0]}"}
    p = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, cwd=root, env=env)
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    return (out.get("permissionDecisionReason") or "") + (out.get("additionalContext") or "")


def answered(text):
    return "devkb, from the graph" in text and "helper" in text


def test_the_unedited_repository_is_answered(repo, tmp_path):
    assert answered(hook(repo, tmp_path))


def test_an_edit_to_a_file_that_never_mentions_the_name_does_not_stale_the_answer_but_a_cited_file_does(repo, tmp_path):
    (repo / "pkg" / "b.py").write_text("def other():\n    return 2\n")                 # unrelated, uncited
    assert answered(hook(repo, tmp_path)), "stale before #409"
    a = repo / "pkg" / "a.py"
    a.write_text("# a comment above shifts every line\n" + a.read_text())               # the answer cites this file's lines
    assert not answered(hook(repo, tmp_path))


def test_an_edit_that_mentions_the_name_stales_it(repo, tmp_path):
    (repo / "pkg" / "b.py").write_text("from pkg.a import helper\n\n\ndef other():\n    return helper(2)\n")
    assert not answered(hook(repo, tmp_path))


def test_a_new_file_stales_it_only_when_it_mentions_the_name(repo, tmp_path):
    (repo / "pkg" / "c.py").write_text("def third():\n    return 3\n")
    assert answered(hook(repo, tmp_path))
    (repo / "pkg" / "d.py").write_text("def fourth():\n    return helper(4)\n")
    assert not answered(hook(repo, tmp_path))


def test_a_deleted_file_that_held_the_name_stales_it(repo, tmp_path):
    (repo / "pkg" / "a.py").unlink()
    assert not answered(hook(repo, tmp_path))


def test_a_commit_that_moves_head_without_touching_the_name_still_answers(repo, tmp_path):
    (repo / "pkg" / "b.py").write_text("def other():\n    return 5\n")
    git(repo, "commit", "-qam", "unrelated")
    assert answered(hook(repo, tmp_path)), "HEAD moved: stale before #409"


def test_a_build_commit_that_git_cannot_find_is_stale(repo, tmp_path):
    m = repo / ".devkb" / "manifest.json"
    d = json.loads(m.read_text())
    d["git_head"] = "0" * 40
    m.write_text(json.dumps(d))
    s = repo / ".devkb" / "symbols-manifest.json"
    d = json.loads(s.read_text())
    d["git_head"] = "0" * 40
    s.write_text(json.dumps(d))
    assert not answered(hook(repo, tmp_path))


def test_many_changed_files_are_stale_without_a_scan(repo, tmp_path):
    for i in range(g.MAX_CHANGED + 2):
        (repo / "pkg" / f"n{i}.py").write_text(f"def n{i}():\n    return {i}\n")
    assert not answered(hook(repo, tmp_path))


def test_cited_paths_are_read_from_answers():
    assert g.CITED.findall("pkg/a.py:3:def helper\n/abs/x.py:9: y\nno path here 12:30") == ["pkg/a.py", "/abs/x.py"]


def test_a_project_in_a_subdirectory_of_the_git_repository(built, tmp_path):      # found by the two-way review of #410
    top = tmp_path / "top"
    proj = top / "proj"
    shutil.copytree(built, proj, ignore=shutil.ignore_patterns(".git"))
    git(top, "init", "-q")
    git(top, "add", ".")
    git(top, "commit", "-qm", "x")
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(proj)], cwd=proj, env=env, check=True, capture_output=True)
    (proj / "pkg" / "b.py").write_text("def other():\n    return 2\n")
    assert answered(hook(proj, tmp_path)), "an unrelated edit must not stale it"
    (proj / "pkg" / "b.py").write_text("from pkg.a import helper\n\n\ndef other():\n    return helper(2)\n")
    assert not answered(hook(proj, tmp_path)), "a changed file that mentions the name must (the paths are relative to the project)"
    assert g.changed_code_files(proj, None) == {"pkg/b.py"}
