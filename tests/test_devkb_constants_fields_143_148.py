"""#143: module constants are symbols whose uses are kept on them. #148: record fields are symbols; string keys are found by function."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "pkg/__init__.py": "",
    "pkg/m.py": (
        "from dataclasses import dataclass\n\n"
        "NAME = 1\nTYPED: int = 2\nlowercase = 3\n\n\n"
        "def own():\n    return NAME\n\n\n"
        "@dataclass\nclass Rec:\n    unresolved_files: list\n    count: int = 0\n\n\n"
        "def write(p):\n    p[\"unresolved_files\"] = [1]\n    return p\n\n\n"
        "def read(p):\n    unresolved_files = 4\n    return p.get(\"unresolved_files\")\n"
    ),
    "pkg/user.py": (
        "from pkg.m import NAME\nfrom pkg import m\n\n\n"
        "def go():\n    lowercase = 1\n    return NAME + m.TYPED + lowercase\n"
    ),
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo")
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    run(root, "build")
    return root


def run(root, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", *args, "--project", str(root)], cwd=root, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-500:]
    return p.stdout


def cli(root, *args):
    return run(root, *args)


def test_constants_resolve_with_line_and_uses(repo):
    out = cli(repo, "symbol", "NAME")
    assert "constant" in out and "L3" in out and "references 2" in out
    assert "constant" in cli(repo, "symbol", "TYPED") and "L4" in cli(repo, "symbol", "TYPED")
    assert "no symbol named" in cli(repo, "symbol", "lowercase")


def test_pack_change_lists_uses(repo):
    out = cli(repo, "pack", "change", "NAME")
    assert "Defined at `pkg/m.py:3" in out
    assert "Uses of the constant (2)" in out and "pkg/user.py:7" in out and "pkg/m.py:9" in out
    assert "Uses of the constant (1)" in cli(repo, "pack", "change", "TYPED")  # through `m.TYPED`


def test_field_symbol_and_key_uses_by_function(repo):
    assert "field" in cli(repo, "symbol", "Rec.unresolved_files")
    out = cli(repo, "uses", "unresolved_files")
    assert "pkg/m.py  write  writes L19" in out
    assert "pkg/m.py  read  reads L25" in out       # the same-named local variable is not a key use
    assert out.count("reads L") == 1
