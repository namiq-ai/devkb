"""#212: a query on a repository with no graph prints one line that says to build first, and exits non-zero."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_a_query_without_a_graph_says_so_in_one_line(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=tmp_path, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    for cmd in (["symbol", "f"], ["uses", "f"], ["outline", "a.py"]):
        p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", *cmd, "--project", str(tmp_path)], cwd=tmp_path, env=env,
                           capture_output=True, text=True)
        assert p.returncode != 0 and "Traceback" not in p.stderr, (cmd, p.stderr[-300:])
        lines = [l for l in p.stderr.splitlines() if l.strip()]
        assert len(lines) == 1 and "devkb build --project" in lines[0], (cmd, p.stderr)
