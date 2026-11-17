from __future__ import annotations
# Hidden acceptance for #70 (from d554ad0).
"""Audit 0.2.5 -> 0.2.8: caller counts and refactor packs say what really uses a function (#69, #70)."""




import os


import subprocess


import sys


from pathlib import Path


import pytest


ROOT = Path(__file__).resolve().parents[1]


sys.path.insert(0, str(ROOT))


from devkb import process_api  # noqa: E402


from devkb.packs import Packer  # noqa: E402




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
    assert m["callers"] == 0, m


def test_a_recursive_method_counts_its_other_callers_only(api):  # #70
    m = api.call("symbol", query="walk")["matches"][0]
    assert m["callers"] == 1, m


def test_the_refactor_pack_does_not_list_a_recursive_call_as_a_caller(api):  # #70
    text = Packer(api).refactor("field_type")
    assert "## Files with a direct caller (0" in text, text

