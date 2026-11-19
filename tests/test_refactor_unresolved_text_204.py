"""#204: `pack refactor` on a name the graph cannot resolve gives the text matches, as `pack change` does."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_unresolved_refactor_gives_the_text_matches(tmp_path):
    (tmp_path / "a.py").write_text("handler = make()\n\n\ndef go():\n    return handler.dispatch_event(1)\n")
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=tmp_path, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(tmp_path)], cwd=tmp_path, env=env, check=True, capture_output=True)
    out = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "pack", "refactor", "dispatch_event", "--project", str(tmp_path)],
                         cwd=tmp_path, env=env, capture_output=True, text=True).stdout
    assert "cannot resolve" in out and "Text matches (not resolved" in out and "a.py" in out
