"""Audit 0.2.5 -> 0.2.8: a source module named test_*.py is source when the project's pytest configuration says
where its tests are (#71)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import process_api  # noqa: E402
from devkb.packs import Packer  # noqa: E402
from devkb.test_discovery import pytest_testpaths  # noqa: E402

FILES = {
    "pytest.ini": "[pytest]\ntestpaths = tests\n",
    "pkg/test_discovery.py": "from pkg.core import match_close\n\n\ndef discover(x):\n    return match_close(x)\n",
    "pkg/core.py": "def match_close(x):\n    return x\n",
    "tests/test_core.py": "from pkg.core import match_close\n\n\ndef test_match_close():\n    assert match_close(1) == 1\n",
}


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    root = tmp_path_factory.mktemp("audittestpaths")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "fixture"], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return process_api.ProcessAPI(str(root), telemetry=False)


def test_a_test_named_module_outside_testpaths_is_a_production_caller(api):
    text = Packer(api).refactor("match_close")
    assert "## Test files among them (1)\n- `tests/test_core.py`" in text, text
    sym = api.call("symbol", query="match_close")["matches"][0]
    assert sym["callers"] == 1, sym


@pytest.mark.parametrize("name, text, want", [
    ("pytest.ini", "[pytest]\ntestpaths = tests\n    integration\n", ("tests", "integration")),
    pytest.param("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests", "more/tests"]\n', ("tests", "more/tests"),
                 marks=pytest.mark.skipif(sys.version_info < (3, 11), reason="no tomllib before Python 3.11")),
    ("setup.cfg", "[tool:pytest]\ntestpaths = t\n", ("t",)),
    ("tox.ini", "[pytest]\ntestpaths = t2\n", ("t2",)),
    ("pyproject.toml", "[project]\nname = 'x'\n", ()),
])
def test_testpaths_are_read_from_each_pytest_configuration_file(tmp_path, name, text, want):
    (tmp_path / name).write_text(text)
    assert pytest_testpaths(tmp_path) == want


def test_without_a_configuration_the_file_name_still_decides():
    assert process_api.is_test_path("pkg/test_discovery.py")
    assert process_api.is_test_path("pkg/test_discovery.py", ("tests",)) is False
    assert process_api.is_test_path("tests/sub/test_x.py", ("tests",)) and process_api.is_test_path("other/tests/helper.py", ("tests",))
