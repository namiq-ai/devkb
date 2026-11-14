"""ODSF-312: a call through an object resolves when the code states the object's class, and never by a guess.

The OCO workflow benchmark found `RuntimeStore.add_edge` with 1 caller in the graph and 16 caller files in the source:
every missed call was `self._store.add_edge(...)` or `store.add_edge(...)`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols  # noqa: E402

FILES = {
    "backend/app/__init__.py": "",
    "backend/app/store.py": ("class RuntimeStore:\n    def add_edge(self, a, b):\n        pass\n\n    @classmethod\n"
                             "    def create(cls):\n        return cls()\n\n\nclass Other:\n    def add_edge(self, a, b):\n        pass\n"),
    "backend/app/service.py": ("from app.store import RuntimeStore\n\n\nclass Planner:\n    def __init__(self, store: RuntimeStore):\n"
                               "        self._store = store\n\n    def plan(self):\n        self._store.add_edge(1, 2)\n\n\n"
                               "def make():\n    return RuntimeStore.create()\n\n\ndef untyped(store):\n    store.add_edge(1, 2)\n"),
    "tests/test_store.py": ("from app.store import RuntimeStore\n\n\ndef test_adds():\n    s = RuntimeStore()\n    s.add_edge(1, 2)\n\n\n"
                            "def test_factory():\n    s = factory()\n    s.add_edge(1, 2)\n"),
}


def test_calls_through_typed_receivers_resolve_and_untyped_ones_do_not(tmp_path):
    for rel, text in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    g = build_symbols.extract(tmp_path)
    into = {e.src for e in g.edges("CALLS") if e.dst == "backend/app/store.py::RuntimeStore.add_edge"}
    assert into == {"backend/app/service.py::Planner.plan", "tests/test_store.py::test_adds"}
    assert not any(e.dst == "backend/app/store.py::Other.add_edge" for e in g.edges("CALLS")), "the class decides, not the name"
    assert ("backend/app/service.py::make", "backend/app/store.py::RuntimeStore.create") in {(e.src, e.dst) for e in g.edges("CALLS")}
