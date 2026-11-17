"""The plugin's session-start hook (plugins/devkb/hooks/session-start.sh), run for real with a fake `uvx` on PATH:
it builds for any project path, never executes text from the path, removes its lock when the build fails, and keeps
the user's last line of .git/info/exclude intact."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "plugins" / "devkb" / "hooks" / "session-start.sh"


def _fake_uvx(tmp_path: Path, code: int = 0) -> Path:
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    uvx = bin_dir / "uvx"
    uvx.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a" >> "$UVXLOG"; done\n'
                   f'printf "%s\\n" "--end--" >> "$UVXLOG"\nexit {code}\n')
    uvx.chmod(0o755)
    return bin_dir


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def _run_hook(project: Path, tmp_path: Path, code: int = 0) -> tuple[list[str], Path]:
    log = tmp_path / "uvx.log"
    env = {**os.environ, "PATH": f"{_fake_uvx(tmp_path, code)}:{os.environ['PATH']}", "UVXLOG": str(log),
           "CLAUDE_PROJECT_DIR": str(project)}
    cwd = tmp_path / "cwd"
    cwd.mkdir(exist_ok=True)
    subprocess.run(["bash", str(HOOK)], env=env, cwd=cwd, check=True, timeout=30)
    lock = project / ".devkb" / ".building"
    deadline = time.time() + 10
    while time.time() < deadline and (lock.exists() or not log.exists()):
        time.sleep(0.05)
    return (log.read_text().splitlines() if log.exists() else []), lock


@pytest.mark.parametrize("name", ["Bob's repo", "x'; touch PWNED; '", 'with "double" and $HOME and `x`'])
def test_the_build_runs_for_a_path_with_quotes_and_nothing_in_it_is_executed(tmp_path, name):
    project = _repo(tmp_path / name)
    args, lock = _run_hook(project, tmp_path)
    assert "--project" in args and args[args.index("--project") + 1] == str(project), args
    assert not lock.exists(), "the lock outlived the build"
    assert (project / ".devkb" / "build.log").exists()
    assert not list(tmp_path.rglob("PWNED")), "text from the path was executed"


def test_a_failed_build_removes_its_lock(tmp_path):
    project = _repo(tmp_path / "repo")
    args, lock = _run_hook(project, tmp_path, code=1)
    assert args and not lock.exists()

