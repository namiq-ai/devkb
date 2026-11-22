"""#285: a one-file grep with a head, a stderr redirect or a leading cd is logged with its file; an output that stops being the file's lines is not; and a match
in an Allman-style C/C++ body names its function."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("devkb_guardrail", ROOT / "scripts" / "devkb_guardrail.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)
from devkb import misses  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "x.rb").write_text("def foo_bar\n  1\nend\n")
    (tmp_path / "a.cc").write_text("int Foo::bar(int x)\n{\n    return x + helper(x);\n}\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


@pytest.mark.parametrize("cmd, rel", [
    ("grep -n foo_bar lib/x.rb | head -5", "lib/x.rb"),
    ("grep -n foo_bar lib/x.rb | tail -n 3", "lib/x.rb"),
    ("grep -n foo_bar lib/x.rb 2>&1", "lib/x.rb"),
    ("grep -n foo_bar lib/x.rb 2>/dev/null", "lib/x.rb"),
    ("grep -n foo_bar lib/x.rb 2>&1 | head -3", "lib/x.rb"),
    ("cd lib && grep -n foo_bar x.rb", "lib/x.rb"),
    ("cd lib && grep -n foo_bar x.rb 2>/dev/null | head", "lib/x.rb"),
    ("grep -n foo_bar lib/x.rb", "lib/x.rb"),
    ("echo hi | grep -n foo_bar lib/x.rb", "lib/x.rb"),             # grep reads its file operand, not the pipe
])
def test_these_forms_are_a_one_file_search_of_that_file(repo, cmd, rel):
    assert g.single_bash_file(cmd, repo, repo) == rel


@pytest.mark.parametrize("cmd", [
    "grep -n foo_bar lib/x.rb | wc -l", "grep -n foo_bar lib/x.rb | cut -d: -f1", "grep -n foo_bar lib/x.rb | sort -u",
    "grep -n foo_bar lib/x.rb > out.txt", "grep -n foo_bar lib/x.rb >> out.txt", "grep -n foo_bar lib/x.rb &> out.txt",
    "grep -n foo_bar lib/x.rb 1>/dev/null", "cd lib && grep -n foo_bar x.rb | awk '{print $1}'",
    "grep -n foo_bar lib/x.rb; ls", "grep -n foo_bar lib/x.rb && echo done", "(grep -n foo_bar lib/x.rb)", "cd nowhere && grep -n foo_bar x.rb",
])
def test_an_output_that_is_no_longer_the_files_numbered_lines_is_not(repo, cmd):
    assert g.single_bash_file(cmd, repo, repo) is None, cmd


def test_a_match_inside_an_allman_style_body_names_its_function(repo):
    assert misses.enclosing(repo, "a.cc", 3, {}) == "Foo::bar"
    assert misses.enclosing(repo, "a.cc", 1, {}) == ""                 # the header line itself is at the top level
