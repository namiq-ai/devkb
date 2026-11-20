"""#286: a call through `from .sub import *` in a package `__init__` is attributed to the function in `sub`; before, the
callers were missing and the pack still said Complete."""
from __future__ import annotations

import subprocess

import pytest

from devkb import build_symbols

SUB = "__all__ = ['starfn']\n\n\ndef starfn():\n    return 3\n"
USER = "import pkg\nfrom pkg import starfn\n\n\ndef c():\n    return starfn()\n\n\ndef g():\n    return pkg.starfn()\n"


def _build(tmp_path, init, sub=SUB, extra=None):
    files = {"pkg/__init__.py": init, "pkg/sub.py": sub, "pkg/user.py": USER, **(extra or {})}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    return build_symbols.extract(tmp_path)


def _callers(g, target):
    return {e.src for e in g.edges("CALLS") if e.dst == target}


@pytest.mark.parametrize("init", ["from .sub import *\n", "from pkg.sub import *\n"])
def test_star_reexport_callers_attributed(tmp_path, init):
    assert _callers(_build(tmp_path, init), "pkg/sub.py::starfn") == {"pkg/user.py::c", "pkg/user.py::g"}


def test_star_reexport_without_all_and_two_hops(tmp_path):
    g = _build(tmp_path, "from .mid import *\n", sub="def starfn():\n    return 3\n", extra={"pkg/mid.py": "from .sub import *\n"})
    assert _callers(g, "pkg/sub.py::starfn") == {"pkg/user.py::c", "pkg/user.py::g"}


def test_named_reexport_still_attributed(tmp_path):
    g = _build(tmp_path, "from .sub import starfn\n")
    assert _callers(g, "pkg/sub.py::starfn") == {"pkg/user.py::c", "pkg/user.py::g"}
