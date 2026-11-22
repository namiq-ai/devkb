"""#297: a retry's push over its own earlier auto branch is accepted. #298: a hanging sandboxed test fails its item. #299: the read tree comes from TRIAGE_REPO."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("triage", Path(__file__).resolve().parents[1] / "ops" / "triage" / "triage.py")
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=t@e.x", "-c", "user.name=T", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout


def test_a_retry_pushes_over_its_own_earlier_auto_branch(monkeypatch, tmp_path):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(tmp_path, "init", "-q", str(work))
    (work / "f").write_text("1\n")
    _git(work, "add", "f")
    _git(work, "commit", "-qm", "base")
    monkeypatch.setattr(triage, "REPO_URL", str(remote))
    gd = work / ".git"
    _git(work, "checkout", "-q", "-B", "auto/5-x")
    (work / "f").write_text("first attempt\n")
    _git(work, "commit", "-qam", "attempt 1")
    triage.push_auto_branch(work, gd, "auto/5-x")
    _git(work, "checkout", "-q", "-B", "auto/5-x", "HEAD~1")             # the retry starts the branch afresh (#207)
    (work / "f").write_text("second attempt\n")
    _git(work, "commit", "-qam", "attempt 2")
    triage.push_auto_branch(work, gd, "auto/5-x")                         # is not a fast-forward; must not be rejected
    assert "second attempt" in _git(remote, "show", "auto/5-x:f")


def test_only_the_daemons_own_branches_are_overwritten(monkeypatch, tmp_path):
    monkeypatch.setattr(triage, "run", lambda *a, **k: pytest.fail("a push was attempted"))
    for bad in ("main", "master", "feature/x", "release/0.2.15"):
        with pytest.raises(RuntimeError):
            triage.push_auto_branch(tmp_path, tmp_path / ".git", bad)


def test_a_timed_out_sandbox_command_is_an_ordinary_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(triage.shutil, "which", lambda n: "/usr/bin/bwrap")
    monkeypatch.setattr(triage, "python_dirs", lambda: [])
    monkeypatch.setattr(triage, "interpreter_links", lambda: [])
    monkeypatch.setattr(triage, "sandbox_python", lambda: "python3")

    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(triage.subprocess, "run", hang)
    with pytest.raises(RuntimeError, match="timed out"):             # RuntimeError: the handle loop marks the item handler-failed and goes on
        triage.sandboxed(["{python}", "-m", "pytest"], tmp_path)


def test_the_read_tree_is_fetched_from_the_repository_the_daemon_serves(monkeypatch, tmp_path):
    cmds = []
    monkeypatch.setattr(triage, "HOME", tmp_path / "home")
    monkeypatch.setattr(triage, "TREE", tmp_path / "home" / "devkb")
    monkeypatch.setattr(triage, "REPO_URL", "https://github.com/someone-else/other-project.git")
    monkeypatch.setattr(triage, "run", lambda cmd, **k: cmds.append(list(cmd)) or "")
    triage.update_tree()
    flat = [" ".join(c) for c in cmds]
    assert any("fetch" in c and "someone-else/other-project.git" in c for c in flat), flat
    assert not any(" origin" in c for c in flat), flat
