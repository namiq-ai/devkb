"""#109: a Python file the build cannot read is named (stderr, symbols-manifest.json, `outline`), never dropped silently.
Python 3.11's parser overflows on a deeply nested expression where 3.12 parses it; the overflow is simulated here so the
test means the same on every interpreter."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import build_symbols, process_api  # noqa: E402
from devkb.read_tools import ReadTools, render_outline  # noqa: E402

FILES = {
    "pkg/__init__.py": "",
    "pkg/good.py": "def ok():\n    return 1\n",
    "pkg/broken.py": "def ok(:\n    return 1\n",
}


def test_a_parser_overflow_is_named_not_silent(tmp_path, capsys, monkeypatch):
    f = tmp_path / "deep.py"
    f.write_text("def ok():\n    return 1\n")

    class Ast:                    # build_symbols' own view of `ast`, whose parser overflows as 3.11's does on
        def __getattr__(self, name):   # sympy's resolvent_lookup.py; pytest's own `ast` stays untouched
            return getattr(ast, name)

        @staticmethod
        def parse(*a, **k):
            raise RecursionError

    monkeypatch.setattr(build_symbols, "ast", Ast())
    skipped: dict[str, str] = {}
    assert build_symbols._parse_python_file(f, skipped)[0] == []
    assert "deep.py: nested too deeply to read" in capsys.readouterr().err
    assert skipped == {str(f): "nested too deeply to read"}


def test_a_syntax_error_is_named_with_its_line(tmp_path, capsys):
    f = tmp_path / "bad.py"
    f.write_text("x = 1\ndef ok(:\n")
    build_symbols._parse_python_file(f)
    assert "bad.py: syntax error at line 2" in capsys.readouterr().err


def test_past_the_limit_the_warnings_stop_but_the_record_does_not(tmp_path, capsys):
    skipped: dict[str, str] = {}
    for n in range(build_symbols.SKIP_PRINT_LIMIT + 5):
        f = tmp_path / f"bad{n}.py"
        f.write_text("def (\n")
        build_symbols._parse_python_file(f, skipped)
    assert len(skipped) == build_symbols.SKIP_PRINT_LIMIT + 5
    assert capsys.readouterr().err.count("devkb: skipped") == build_symbols.SKIP_PRINT_LIMIT


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo")
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    p = subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-800:]
    return root, p.stderr


def test_the_build_names_the_file_and_the_manifest_keeps_it(built):
    root, err = built
    assert "broken.py: syntax error at line 1" in err
    manifest = json.loads((root / ".devkb" / "symbols-manifest.json").read_text())
    assert list(manifest["skipped_files"]) == ["pkg/broken.py"]


def test_outline_says_the_file_could_not_be_read(built):
    root, _ = built
    tools = ReadTools(process_api.ProcessAPI(str(root), telemetry=False))
    for query in ("pkg/broken.py", "broken.py"):
        text = render_outline(tools.outline(query))
        assert "not indexed, the build could not read it (syntax error at line 1" in text, text
    assert "ok" in render_outline(tools.outline("pkg/good.py"))
