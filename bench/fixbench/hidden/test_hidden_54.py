from __future__ import annotations
# Hidden acceptance for #54 (from 734b374).
"""Audit 0.2.5 -> 0.2.8: the read tools answer about every tracked path and never call a failed search "no match"
(#54, #55)."""




import os


import subprocess


import sys


from pathlib import Path


import pytest


ROOT = Path(__file__).resolve().parents[1]


sys.path.insert(0, str(ROOT))


from devkb import process_api  # noqa: E402


FILES = {
    ".github/scripts/tool.py": "def gh_tool(x):\n    return x\n",
    "pkg/app.py": "def run():\n    return 1\n",
    "docs/pricing.md": "# Pricing\n\nPrice ($) per seat.\n",
}


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    root = tmp_path_factory.mktemp("auditread")
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


@pytest.mark.parametrize("path", [".github/scripts/tool.py", "./.github/scripts/tool.py"])
def test_outline_finds_a_file_under_a_dot_directory(api, path):  # #54
    r = api.call("outline", path=path)
    assert r.get("path") == ".github/scripts/tool.py" and [s["name"] for s in r["symbols"]] == ["gh_tool"], r


@pytest.mark.parametrize("query", [".github/scripts/tool.py::gh_tool", "./.github/scripts/tool.py::gh_tool"])
def test_symbol_finds_a_definition_under_a_dot_directory(api, query):  # #54
    r = api.call("symbol", query=query)
    assert [m["k"] for m in r["matches"]] == [".github/scripts/tool.py::gh_tool"], r

