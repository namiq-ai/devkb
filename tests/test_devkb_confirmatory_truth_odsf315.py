"""ODSF-315: the confirmatory study's truth resolves calls by module path, so equal names in different modules never
meet, and an external repository is reachable only on explicit request."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "devkb" / "bench"))

import module_truth as mt  # noqa: E402

from devkb import project_context  # noqa: E402

FILES = {
    "app/__init__.py": "", "app/incident/__init__.py": "", "app/case/__init__.py": "",
    "app/incident/service.py": "def get(x):\n    if not x:\n        raise ValueError('an incident needs an id here')\n    return x\n",
    "app/case/service.py": "def get(x):\n    return x\n",
    "app/incident/views.py": ("from app.incident import service\n\n\n@router.get('/incidents/{i}')\ndef read_incident(i):\n"
                              "    return service.get(i)\n"),
    "app/case/views.py": "from app.case.service import get\n\n\n@router.get('/cases/{i}')\ndef read_case(i):\n    return get(i)\n",
    "tests/test_incident.py": "import app.incident.service as svc\n\n\ndef test_get():\n    assert svc.get(1)\n",
}


def _repo(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def test_equal_names_in_different_modules_never_meet(tmp_path):
    t = mt.Truth(_repo(tmp_path))
    c = t.callers()
    assert c[("app/incident/service.py", "get")] == {("app/incident/views.py", "read_incident"), ("tests/test_incident.py", "test_get")}
    assert c[("app/case/service.py", "get")] == {("app/case/views.py", "read_case")}


def test_a_chain_ends_at_a_route_handler_and_counts_its_tests(tmp_path):
    t = mt.Truth(_repo(tmp_path))
    prod, tests, clean = t.up(("app/incident/service.py", "get"))
    assert clean and prod == {("app/incident/views.py", "read_incident")} and tests == {("tests/test_incident.py", "test_get")}
    assert t.is_route(("app/incident/views.py", "read_incident"))


def test_an_external_repository_is_never_a_silent_default(tmp_path):
    with pytest.raises(ValueError):
        project_context.resolve("NOT-REGISTERED-315")
    ctx = project_context.external_context("C", tmp_path, tmp_path / "g")
    assert ctx.repo_root == tmp_path.resolve() and ctx.devkb_dir == tmp_path / "g"
