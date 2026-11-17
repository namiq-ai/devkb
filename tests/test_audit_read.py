"""Audit 0.2.5 -> 0.2.8: the read tools answer about every tracked path and never call a failed search "no match"
(#54, #55)."""
from __future__ import annotations

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
    "pkg/many.py": (
        "# several notes: several is mentioned here\n"
        "# several again\n"
        '"""Module doc mentioning several."""\n'
        "\n"
        "\n"
        "def several(x):\n"
        '    """several: a docstring\n'
        "    that says several twice.\n"
        '    """\n'
        "    return x\n"
        "\n"
        "\n"
        "def caller_a():\n"
        "    # use several here\n"
        "    return several(1)  # several\n"
        "\n"
        "\n"
        "def caller_b():\n"
        "    return several(2)\n"
        "\n"
        "\n"
        "def caller_c():\n"
        "    return several (3)\n"
    ),
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


def test_search_docs_reports_a_pattern_git_grep_rejects_as_an_error_not_as_no_match(api):  # #55
    r = api.call("search_docs", query="Price ($")
    assert "error" in r and "Price ($" in r["error"], r
    assert api.call("search_docs", query="Price")["n_files"] == 1, "a valid query still finds the doc"


@pytest.mark.parametrize("path", [".github/scripts/tool.py", "./.github/scripts/tool.py"])
def test_the_file_pack_finds_a_file_under_a_dot_directory(api, path):  # #86
    from devkb.packs import Packer  # noqa: PLC0415
    text = Packer(api).file(path)
    assert "# Graph pack: before editing `.github/scripts/tool.py`" in text, text


def test_a_cpp_include_into_a_dot_directory_resolves_and_parent_steps_still_drop():  # #86
    from devkb.cpp_graph import _Includers  # noqa: PLC0415
    inc = _Includers([".gen/config.h", "include/api.h"])
    assert inc.resolve("src/a.c", ".gen/config.h") == [".gen/config.h"]
    assert inc.resolve("src/a.c", "./.gen/config.h") == [".gen/config.h"]
    assert inc.resolve("lib/deep/b.c", "../include/api.h") == ["include/api.h"]


def test_a_path_literal_into_a_dot_directory_resolves_a_call():  # #86
    from devkb.build_symbols import _resolve_via_literals  # noqa: PLC0415
    table = {".github/scripts/tool.py": [{"qualified_name": "gh_tool"}], "pkg/app.py": [{"qualified_name": "run"}]}
    assert _resolve_via_literals([".github/scripts/tool.py"], "gh_tool", table) == ".github/scripts/tool.py::gh_tool"
    assert _resolve_via_literals(["./.github/scripts/tool.py"], "gh_tool", table) == ".github/scripts/tool.py::gh_tool"
    assert _resolve_via_literals(["../pkg/app.py"], "run", table) == "pkg/app.py::run"


def test_uses_keeps_the_calls_when_comments_and_docstrings_come_first_in_a_file(api):  # #89
    r = api.call("uses", name="several")
    hits = next(f for f in r["files"] if f["f"] == "pkg/many.py")["hits"]
    assert [h["line"] for h in hits] == [15, 19, 23], hits  # the three calls, in line order; not the definition or prose


@pytest.mark.parametrize("under", ["pkg/many.py", "./pkg/many.py"])
def test_uses_under_a_file_path_searches_that_file(api, under):  # #90
    r = api.call("uses", name="several", under=under)
    assert [f["f"] for f in r["files"]] == ["pkg/many.py"] and r["n_hits"] >= 3, r
    assert api.call("uses", name="several", under="pkg")["n_hits"] == r["n_hits"], "a directory still works"
