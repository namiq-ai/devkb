"""The three defects of the two-way review of PR #407, each failing without its fix."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "bench" / "audit"))
import devkb_guardrail as g  # noqa: E402
import toolmix as t  # noqa: E402


def test_cat_n_renumbers_the_lines_so_the_search_is_not_replaced(tmp_path):
    (tmp_path / "b.py").write_text("x\n")
    assert g.single_bash_file("grep -n x b.py | cat -n", tmp_path, tmp_path) is None
    assert g.single_bash_file("grep -n x b.py | cat -b", tmp_path, tmp_path) is None
    assert g.single_bash_file("grep -n x b.py | cat", tmp_path, tmp_path) is not None, "a bare cat copies the lines"
    assert g.single_bash_file("grep -n x b.py | head -5", tmp_path, tmp_path) is not None


def test_an_apostrophe_is_not_a_quote():
    assert t.devkb_queries("echo don't; devkb symbol x") == 1
    assert t.devkb_queries("git commit -m 'devkb symbol x'") == 0, "a real quote still hides prose"
    assert t.devkb_queries("echo it's fine 'and' devkb symbol x") == 1


@pytest.mark.parametrize("module", ["query", "audit", "coverage"])
def test_a_module_run_with_no_graph_prints_one_line_and_exits_2(module):
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([sys.executable, "-m", f"devkb.{module}", "--project", d] + (["--about", "X"] if module == "query" else []),
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)}, cwd=d)
    assert r.returncode == 2 and "Traceback" not in r.stderr and "devkb build" in r.stderr, (r.returncode, r.stderr[-300:])
