"""#128: `uses` on a name with a regex character searches it literally instead of answering with git's error."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_a_name_with_a_bracket_is_searched_literally(tmp_path):
    (tmp_path / "a.py").write_text("class ProcessAPI:\n    pass\n\n\ndef go():\n    return ProcessAPI()\n")
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=tmp_path, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(tmp_path)], cwd=tmp_path, env=env, check=True, capture_output=True)
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "uses", "ProcessAPI(", "--project", str(tmp_path)], cwd=tmp_path,
                       env=env, capture_output=True, text=True)
    out = p.stdout + p.stderr
    assert "fatal" not in out and "Unmatched" not in out and "a.py:6" in out
