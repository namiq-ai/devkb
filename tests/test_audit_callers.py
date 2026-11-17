"""Audit 0.2.5 -> 0.2.8: caller counts and refactor packs say what really uses a function (#69, #70)."""
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
from devkb.read_tools import RENDER  # noqa: E402

FILES = {
    "pkg/index.py": (
        "class Index:\n"
        "    def field_type(self, names, name):\n"
        "        if not names:\n"
        "            return None\n"
        "        return self.field_type(names[1:], name)\n"
        "\n"
        "    def walk(self, n):\n"
        "        return 0 if n <= 0 else self.walk(n - 1)\n"
        "\n"
        "\n"
        "def use():\n"
        "    return Index().walk(3)\n"
    ),
    "pkg/work.py": (
        "from concurrent.futures import ThreadPoolExecutor\n"
        "\n"
        "\n"
        "class Worker:\n"
        "    def _moved_files(self, rev):\n"
        "        return rev\n"
        "\n"
        "    def run(self, rev):\n"
        "        with ThreadPoolExecutor() as pool:\n"
        "            return pool.submit(self._moved_files, rev).result()\n"
        "\n"
        "\n"
        "def key_of(x):\n"
        "    return x\n"
        "\n"
        "\n"
        "def order(xs, key_of_local=None):\n"
        "    return sorted(xs, key=key_of)\n"
        "\n"
        "\n"
        "def plain():\n"
        "    return 1\n"
        "\n"
        "\n"
        "def shadowed(plain):\n"
        "    return [plain, plain()]\n"
        "\n"
        "\n"
        "def use():\n"
        "    return plain()\n"
    ),
    "pkg/calc.py": (
        "class Calc:\n"
        "    def compute(self, x):\n"
        "        return x\n"
        "\n"
        "\n"
        "def direct():\n"
        "    return Calc().compute(1)\n"
        "\n"
        "\n"
        "def via(obj):\n"
        "    return obj.compute(2)\n"
    ),
}


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    root = tmp_path_factory.mktemp("auditcallers")
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


def test_a_method_that_only_calls_itself_has_no_callers(api):  # #70
    r = api.call("symbol", query="field_type")
    m = r["matches"][0]
    assert m["callers"] == 0 and m.get("self_call") is True, m
    assert "callers 0 (+ itself)" in RENDER["symbol"](r)


def test_a_recursive_method_counts_its_other_callers_only(api):  # #70
    m = api.call("symbol", query="walk")["matches"][0]
    assert m["callers"] == 1 and m.get("self_call") is True, m


def test_the_refactor_pack_does_not_list_a_recursive_call_as_a_caller(api):  # #70
    text = Packer(api).refactor("field_type")
    assert "## Files with a direct caller (0" in text and "calls itself" in text, text


@pytest.mark.parametrize("name, line", [("_moved_files", 10), ("key_of", 18)])
def test_a_function_passed_as_a_value_makes_the_refactor_pack_incomplete_and_names_the_line(api, name, line):  # #69
    text = Packer(api).refactor(name)
    assert "**Complete.**" not in text and "**Incomplete" in text, text
    assert f"`pkg/work.py:{line}:" in text and "without a call" in text, text


def test_a_function_only_called_stays_complete_and_a_parameter_of_the_same_name_is_not_a_reference(api):  # #69
    text = Packer(api).refactor("plain")
    assert "**Complete.**" in text and "without a call" not in text, text


def test_symbol_says_a_function_with_no_caller_is_named_without_a_call(api):  # #69
    r = api.call("symbol", query="_moved_files")
    assert "callers 0 (+ named without a call at 1 site(s))" in RENDER["symbol"](r)


def test_symbol_says_its_caller_count_is_a_lower_bound_when_calls_under_the_name_were_not_attributed(api):  # #87
    r = api.call("symbol", query="compute")
    m = r["matches"][0]
    assert m["callers"] == 1 and m.get("unresolved") == 1, m
    assert "callers 1+ (calls under this name from 1 more function(s) not attributed)" in RENDER["symbol"](r)
    assert "not attributed" not in RENDER["symbol"](api.call("symbol", query="plain")), "a fully attributed count says nothing"
