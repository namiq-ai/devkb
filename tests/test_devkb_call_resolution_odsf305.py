"""ODSF-305: devkb resolves the calls a repository actually makes.

Each case builds a throwaway git repo, because extraction is `git ls-files`
over real files. The shapes are the ones the sampled functions failed on:
`from pkg import module` then `module.func()`, `import a.b as m`, a relative
import, a module found through `sys.path.insert`, and a module loaded by path.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols  # noqa: E402
from devkb.extractors import symbol_tests  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _calls(graph) -> set[tuple[str, str]]:
    return {(e.src, e.dst) for e in graph.edges("CALLS")}


LIB = {"lib/__init__.py": "", "lib/store.py": "def save_record(x):\n    return x\n"}


def test_from_package_import_module_then_module_dot_function(tmp_path):
    root = _repo(tmp_path, {**LIB, "app/run.py": "from lib import store\n\ndef go():\n    store.save_record(1)\n"})
    assert ("app/run.py::go", "lib/store.py::save_record") in _calls(build_symbols.extract(root))


def test_aliased_plain_import_resolves_through_the_alias(tmp_path):
    root = _repo(tmp_path, {**LIB, "app/run.py": "import lib.store as st\n\ndef go():\n    st.save_record(1)\n"})
    assert ("app/run.py::go", "lib/store.py::save_record") in _calls(build_symbols.extract(root))


def test_relative_import_is_anchored_on_the_callers_directory(tmp_path):
    root = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/store.py": "def save_record(x):\n    return x\n",
                            "pkg/run.py": "from . import store\n\ndef go():\n    store.save_record(1)\n"})
    assert ("pkg/run.py::go", "pkg/store.py::save_record") in _calls(build_symbols.extract(root))


def test_a_module_reached_through_sys_path_resolves_when_its_name_is_unique(tmp_path):
    root = _repo(tmp_path, {"tools/orch/landing.py": "def land_ticket(x):\n    return x\n",
                            "tests/test_a.py": "import sys\nsys.path.insert(0, 'tools/orch')\nimport landing as sl\n\n"
                                               "def go():\n    sl.land_ticket(1)\n"})
    assert ("tests/test_a.py::go", "tools/orch/landing.py::land_ticket") in _calls(build_symbols.extract(root))


def test_an_ambiguous_module_name_is_not_guessed(tmp_path):
    root = _repo(tmp_path, {"a/util.py": "def helper_fn(x):\n    return x\n", "b/util.py": "def helper_fn(x):\n    return x\n",
                            "c/run.py": "import util\n\ndef go():\n    util.helper_fn(1)\n"})
    assert not [c for c in _calls(build_symbols.extract(root)) if c[0] == "c/run.py::go"]


def test_a_module_loaded_by_its_file_path_resolves_through_the_path_string(tmp_path):
    root = _repo(tmp_path, {"sdp/dev-orchestrator.py": "def load_process(x):\n    return x\n",
                            "tests/test_b.py": "import importlib.util\nspec = importlib.util.spec_from_file_location('o', 'sdp/dev-orchestrator.py')\n"
                                               "orch = importlib.util.module_from_spec(spec)\n\ndef go():\n    orch.load_process(1)\n"})
    assert ("tests/test_b.py::go", "sdp/dev-orchestrator.py::load_process") in _calls(build_symbols.extract(root))


def test_a_test_is_linked_to_the_function_it_calls_through_a_module(tmp_path):
    root = _repo(tmp_path, {**LIB, "tests/test_store.py": "from lib import store\n\ndef test_saves():\n    store.save_record(1)\n"})
    graph = build_symbols.extract(root)
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="TST", issues_dir=root / "issues",
                         tests_dir=root / "tests", sprint_dir=root / "h", devkb_dir=root / ".devkb",
                         board_file=root / "b.md", wp_map_file=root / "w.json")
    linked = {(e.src, e.dst) for e in symbol_tests.extract(ctx, graph).edges("TESTED_BY")}
    assert ("lib/store.py::save_record", "tests/test_store.py:3") in linked


def test_a_call_on_an_unknown_variable_is_left_unresolved(tmp_path):
    root = _repo(tmp_path, {**LIB, "app/run.py": "def go(thing):\n    thing.save_record(1)\n"})
    assert not [c for c in _calls(build_symbols.extract(root)) if c[0] == "app/run.py::go"]
