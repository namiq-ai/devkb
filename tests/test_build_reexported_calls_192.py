"""#192: a call through a package re-export that the resolver leaves unattributed is still counted against the symbol,
so its pack says Incomplete and names the file, instead of Complete with no caller."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _repo(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


def pack(root, *a):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    return subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "pack", *a, "--project", str(root)], cwd=root, env=env,
                          capture_output=True, text=True).stdout


# `run` is both a function and a method `Job.run` in pkg/records.py, so `from pkg import run; run()` through the
# package re-export is left unattributed (the audit's r07 fixture)
FILES = {"pkg/__init__.py": "from .records import run\n",
         "pkg/records.py": "class Job:\n    def run(self):\n        return 0\n\n\ndef run():\n    return 1\n",
         "app/__init__.py": "", "app/user.py": "from pkg import run\n\n\ndef caller():\n    return run()\n",
         "tests/__init__.py": "", "tests/test_user.py": "from app.user import caller\n\n\ndef test_caller():\n    assert caller() == 1\n"}


def test_an_unattributed_call_through_a_reexport_keeps_the_pack_incomplete(tmp_path):
    p = pack(_repo(tmp_path, FILES), "change", "pkg/records.py::run")
    assert "**Complete.**" not in p
    assert "app/user.py" in p
