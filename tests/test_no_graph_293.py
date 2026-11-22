"""#293: audit, coverage and query on a repository with no graph print one line naming `devkb build --project PATH` and exit 2, never a traceback."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    return tmp_path


def _run(tmp_path, *args):
    return subprocess.run([sys.executable, "-m", "devkb.cli", *args, "--project", str(tmp_path)], cwd=ROOT, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "HOME": str(tmp_path)})


def test_every_query_command_prints_the_same_one_line_and_exits_2(tmp_path):
    repo = _repo(tmp_path)
    for cmd in (["audit"], ["coverage"], ["query", "--about", "x"], ["symbol", "f"], ["outline", "a.py"], ["uses", "f"]):
        p = _run(repo, *cmd)
        assert p.returncode == 2, (cmd, p.returncode, p.stderr)
        assert "Traceback" not in p.stderr, (cmd, p.stderr)
        lines = [ln for ln in p.stderr.splitlines() if ln.strip()]
        assert len(lines) == 1 and f"devkb build --project {repo}" in lines[0] and "build.py" not in lines[0], (cmd, p.stderr)
