"""#158: the git hooks rebuild with the devkb that installed them, on merge, rebase and checkout; a build leaves a line in
.devkb/build.log; builds run one at a time; the next read command says when the last build failed."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from devkb import buildlog, init

ROOT = Path(__file__).resolve().parent.parent
ID = ["-c", "user.name=t", "-c", "user.email=t@example.com"]


def _env(home: Path) -> dict:
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    for k in ("DEVKB_DIR", "DEVKB_REPO", "DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG"):
        env.pop(k, None)
    return env


class Repo(type(Path())):
    """A path that also carries `vc` (run version control here) and `env`."""


@pytest.fixture
def repo(tmp_path):
    a = Repo(tmp_path / "a")
    (tmp_path / "home").mkdir()
    a.mkdir()
    env = _env(tmp_path / "home")

    def vc(*args):
        return subprocess.run(["git", *ID, *args], cwd=a, env=env, capture_output=True, text=True, check=True).stdout.strip()
    vc("init", "-q", "-b", "main")
    (a / "m.py").write_text("def foo():\n    return 1\n")
    vc("add", ".")
    vc("commit", "-qm", "x")
    a.vc, a.env = vc, env  # type: ignore[attr-defined]
    return a


def _cli(repo, *args):
    return subprocess.run([sys.executable, "-P", "-m", "devkb.cli", *args], cwd=repo, env=repo.env, capture_output=True,
                          text=True, timeout=120)


def test_init_writes_four_hooks_calling_this_devkb_by_absolute_path(repo):
    init.run(repo, "lean-pack", hooks=True, dry_run=False)
    for name in ("post-commit", "post-merge", "post-checkout", "post-rewrite"):
        text = (repo / ".git" / "hooks" / name).read_text()
        assert sys.executable in text and str(ROOT) in text
        assert "build --hook" in text
        assert not any(w == "devkb" for w in text.replace("(", " ").split())  # never the bare command on PATH


def test_build_leaves_a_log_line_at_head(repo):
    assert _cli(repo, "build", "--project", str(repo)).returncode == 0
    line = (repo / ".devkb" / "build.log").read_text().splitlines()[-1]
    assert f"head={repo.vc('rev-parse', 'HEAD')}" in line and "exit=0" in line and "took=" in line


def test_hook_build_skips_when_the_graph_is_at_head(repo):
    _cli(repo, "build", "--project", str(repo))
    assert _cli(repo, "build", "--hook", "--project", str(repo)).returncode == 0
    assert "skipped" in (repo / ".devkb" / "build.log").read_text().splitlines()[-1]


def test_failed_build_is_logged_and_read_commands_say_so(repo):
    _cli(repo, "build", "--project", str(repo))
    graph = [f for f in (repo / ".devkb").iterdir() if f.suffix in (".json", ".jsonl")]
    for f in graph:
        f.chmod(0o444)
    try:
        (repo / "n.py").write_text("x = 1\n")
        repo.vc("add", ".")
        repo.vc("commit", "-qm", "y")
        assert _cli(repo, "build", "--project", str(repo)).returncode != 0
        assert "exit=0" not in (repo / ".devkb" / "build.log").read_text().splitlines()[-1]
        assert "failed" in (buildlog.last_failure(repo / ".devkb") or "")
        out = _cli(repo, "symbol", "foo", "--project", str(repo))
        assert "last build failed" in out.stdout + out.stderr
    finally:
        for f in graph:
            f.chmod(0o644)
    assert _cli(repo, "build", "--project", str(repo)).returncode == 0  # a good build clears it
    assert buildlog.last_failure(repo / ".devkb") is None


def test_a_second_build_waits_while_one_runs(repo):
    import fcntl
    _cli(repo, "build", "--project", str(repo))
    log = repo / ".devkb" / "build.log"
    before = len(log.read_text().splitlines())
    repo.vc("commit", "-q", "--allow-empty", "-m", "z")
    with open(repo / ".devkb" / "build.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # a build is running
        p = subprocess.Popen([sys.executable, "-P", "-m", "devkb.cli", "build", "--hook", "--project", str(repo)],
                             cwd=repo, env=repo.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        assert p.poll() is None and len(log.read_text().splitlines()) == before
        fcntl.flock(lock, fcntl.LOCK_UN)
    assert p.wait(timeout=60) == 0
    assert f"head={repo.vc('rev-parse', 'HEAD')}" in log.read_text().splitlines()[-1]


def test_installed_hook_returns_at_once_and_builds_in_the_background(repo):
    init.run(repo, "lean-pack", hooks=True, dry_run=False)
    repo.vc("add", ".")
    repo.vc("commit", "-qm", "devkb files")
    deadline = time.time() + 30
    log = repo / ".devkb" / "build.log"
    while time.time() < deadline and not log.exists():
        time.sleep(0.3)
    import fcntl
    with open(repo / ".devkb" / "build.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # even with the lock held elsewhere a commit does not wait for it
        t0 = time.monotonic()
        repo.vc("commit", "-q", "--allow-empty", "-m", "q")
        assert time.monotonic() - t0 < 5
        fcntl.flock(lock, fcntl.LOCK_UN)
    head = repo.vc("rev-parse", "HEAD")
    deadline = time.time() + 40
    while time.time() < deadline and head not in log.read_text():
        time.sleep(0.3)
    assert head in log.read_text()
    assert json.loads((repo / ".devkb" / "manifest.json").read_text())["git_head"] == head
