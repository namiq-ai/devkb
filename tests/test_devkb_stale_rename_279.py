"""#279: a renamed, added or deleted code file in the searched scope makes the graph stale for that search, as a modified one does."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("devkb_guardrail_279", ROOT / "scripts" / "devkb_guardrail.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _git(root, *c):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *c], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def handler(a):\n    return a\n")
    (tmp_path / "pkg" / "use.py").write_text("from pkg.mod import handler\nhandler(1)\n")
    _git(tmp_path, "init", "-q"); _git(tmp_path, "add", "."); _git(tmp_path, "commit", "-qm", "a")
    env = dict(os.environ, PYTHONPATH=str(ROOT), HOME=str(tmp_path / "h"), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(tmp_path)], cwd=tmp_path, env=env,
                   capture_output=True, check=True)
    return tmp_path


def test_clean_tree_is_not_stale(repo):
    assert guard.graph_stale(repo, ["pkg"]) is False


def test_staged_rename_is_stale(repo):
    _git(repo, "mv", "pkg/use.py", "pkg/client.py")
    assert guard.graph_stale(repo, ["pkg"]) is True


def test_staged_delete_is_stale(repo):
    _git(repo, "rm", "-q", "pkg/use.py")
    assert guard.graph_stale(repo, ["pkg"]) is True


def test_staged_add_is_stale(repo):
    (repo / "pkg" / "new.py").write_text("def fresh():\n    return 1\n")
    _git(repo, "add", "pkg/new.py")
    assert guard.graph_stale(repo, ["pkg"]) is True


def test_rename_of_a_non_code_file_is_not_stale(repo):
    (repo / "pkg" / "notes.txt").write_text("a\n")
    _git(repo, "add", "pkg/notes.txt")
    _git(repo, "commit", "-qm", "n")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(repo)], cwd=repo, check=True,
                   capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT), HOME=str(repo / "h")))  # only the rename pending
    _git(repo, "mv", "pkg/notes.txt", "pkg/notes2.txt")
    assert guard.graph_stale(repo, ["pkg"]) is False


def _rebuild(repo):
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(repo)], cwd=repo, check=True,
                   capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT), HOME=str(repo / "h")))


def test_rebuilt_after_a_rename_is_fresh_again(repo):
    _git(repo, "mv", "pkg/use.py", "pkg/client.py")
    assert guard.graph_stale(repo, ["pkg"]) is True
    _rebuild(repo)
    assert guard.graph_stale(repo, ["pkg"]) is False


def test_rebuilt_after_an_add_is_fresh_again(repo):
    (repo / "pkg" / "new.py").write_text("def fresh():\n    return 1\n")
    _git(repo, "add", "pkg/new.py")
    assert guard.graph_stale(repo, ["pkg"]) is True
    _rebuild(repo)
    assert guard.graph_stale(repo, ["pkg"]) is False


def test_rebuilt_after_a_delete_is_fresh_again(repo):
    _git(repo, "rm", "-q", "pkg/use.py")
    assert guard.graph_stale(repo, ["pkg"]) is True
    _rebuild(repo)
    assert guard.graph_stale(repo, ["pkg"]) is False
