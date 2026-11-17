"""#104: the change and refactor packs accept `module.name`, as `symbol` does; #105: a whitespace-only docstring does not
crash the build."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import build_symbols, process_api  # noqa: E402
from devkb.packs import Packer  # noqa: E402

FILES = {
    "pkg/__init__.py": "",
    "pkg/alpha.py": "def extract(x):\n    return x\n",
    "pkg/beta.py": "def extract(x):\n    return x\n",
    "pkg/use.py": "from pkg import alpha\n\n\ndef go():\n    return alpha.extract(1)\n",
    "pkg/blank.py": 'class C:\n    """\n    """\n\n    def m(self):\n        return 1\n',
}


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    import os
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
    assert p.returncode == 0, p.stderr[-800:]          # #105: the whitespace-only docstring in pkg/blank.py
    return process_api.ProcessAPI(str(root), telemetry=False)


def test_a_whitespace_only_docstring_has_no_summary():
    assert build_symbols._first_line("\n    ") is None and build_symbols._first_line(" One. \n more") == "One."
    tree = ast.parse(FILES["pkg/blank.py"])
    assert build_symbols._first_line(ast.get_docstring(tree.body[0], clean=False)) is None


@pytest.mark.parametrize("name", ["alpha.extract", "pkg.alpha.extract"])
def test_the_refactor_pack_accepts_a_module_qualified_name(api, name):
    text = Packer(api).refactor(name)
    assert "cannot resolve" not in text and "pkg/use.py" in text, text


def test_the_change_pack_accepts_a_module_qualified_name(api):
    assert "cannot resolve" not in Packer(api).change("alpha.extract")


def test_a_bare_shared_name_stays_ambiguous(api):
    assert "cannot resolve" in Packer(api).refactor("extract")


def test_a_deeply_nested_file_is_skipped_with_a_warning_not_a_crash(tmp_path, capsys):  # #106
    deep = tmp_path / "deep.py"
    # parses (a flat chain, like sympy's generated resolvent tables) but nests thousands of levels deep in the tree
    deep.write_text("x = " + " + ".join(["a"] * 5000) + "\n\n\ndef ok():\n    return 1\n")
    try:
        out = build_symbols._parse_python_file(deep)
    except RecursionError:
        pytest.fail("RecursionError escaped")
    assert out[0] == [] or any(s.get("name") == "ok" for s in out[0])
    assert "deep.py" in capsys.readouterr().err or out[0], "a skipped file is named, never silent"
