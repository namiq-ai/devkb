"""#196, #197: a pack for a module constant lists the functions that read it, their tests, and says Incomplete when a
star import reads it unattributed; `pack refactor` (the command AGENTS.md names) lists the reading files too."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = {"pkg/__init__.py": "",
         "pkg/settings.py": "RETRIES = 3\n",
         "pkg/use_from.py": "from pkg.settings import RETRIES\n\n\ndef f():\n    return RETRIES + 1\n",
         "pkg/use_star.py": "from pkg.settings import *\n\n\ndef h():\n    return RETRIES * 2\n",
         "tests/__init__.py": "",
         "tests/test_f.py": "from pkg.use_from import f\n\n\ndef test_f():\n    assert f()\n"}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r196")
    for rel, t in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(t)
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


def pack(root, *a):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    return subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "pack", *a, "--project", str(root)], cwd=root, env=env,
                          capture_output=True, text=True).stdout


def test_change_pack_lists_readers_tests_and_the_star_import_gap(repo):
    p = pack(repo, "change", "RETRIES")
    assert "pkg/use_from.py::f" in p and "tests/test_f.py" in p
    assert "**Complete.**" not in p and "pkg/use_star.py" in p


def test_refactor_pack_lists_the_files_that_read_it(repo):
    p = pack(repo, "refactor", "RETRIES")
    assert "pkg/use_from.py" in p and "reads it at" in p and "**Complete.**" not in p
