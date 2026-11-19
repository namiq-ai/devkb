"""#193: a dataclass field (or a module constant) named like a function never takes that function's calls."""
import subprocess
from pathlib import Path

from devkb import build_symbols


def _repo(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=root, check=True)
    return root


def calls(g):
    return {(e.src, e.dst) for e in g.edges("CALLS")}


def test_a_same_file_field_does_not_shadow_the_function(tmp_path):
    g = build_symbols.extract(_repo(tmp_path, {"pkg/__init__.py": "", "pkg/records.py": (
        "from dataclasses import dataclass\n\n\n@dataclass\nclass Job:\n    run: int = 0\n\n\n"
        "def run():\n    return 1\n\n\ndef caller():\n    return run()\n")}))
    assert ("pkg/records.py::caller", "pkg/records.py::run") in calls(g)


def test_a_field_in_the_imported_module_does_not_shadow_the_function(tmp_path):
    g = build_symbols.extract(_repo(tmp_path, {"pkg/__init__.py": "", "pkg/records.py": (
        "from dataclasses import dataclass\n\n\n@dataclass\nclass Job:\n    run: int = 0\n\n\ndef run():\n    return 1\n"),
        "app/__init__.py": "", "app/user.py": "from pkg.records import run\n\n\ndef caller():\n    return run()\n"}))
    assert ("app/user.py::caller", "pkg/records.py::run") in calls(g)


def test_a_constant_named_like_a_function_does_not_take_its_calls(tmp_path):
    g = build_symbols.extract(_repo(tmp_path, {"pkg/__init__.py": "", "pkg/m.py": (
        "def limit():\n    return 3\n\n\ndef caller():\n    return limit()\n\n\nLIMIT = 3\n")}))
    assert ("pkg/m.py::caller", "pkg/m.py::limit") in calls(g)
