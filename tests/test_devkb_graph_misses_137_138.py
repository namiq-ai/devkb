"""#137: a miss from a search of one file keeps that file's name, also with context or count options and from the Grep
tool. #138: each match names the function that holds it from the graph's own spans, also under a multi-line header."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import devkb_guardrail as g  # noqa: E402
from devkb import misses  # noqa: E402

C_A = ("static int\nhelper(int x,\n       int y)\n{\n    return x + y;\n}\n\n"
       "static int\ncaller_c(int x,\n         int y)\n{\n    int z = x;\n    return helper(z, y);\n}\n")


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r137")
    (root / "src").mkdir()
    (root / "src" / "a.c").write_text(C_A)
    (root / "src" / "b.c").write_text("static int helper(int x, int y)\n{\n    return x - y;\n}\n")
    (root / "m.py").write_text("def caller_py(\n    a,\n):\n    b = a\n    return helper(b)\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env,
                   check=True, capture_output=True)
    return root


@pytest.mark.parametrize("cmd", ["grep -rn helper src/a.c", "grep -n -A2 helper src/a.c", "grep -nA2 helper src/a.c",
                                 "grep -m 5 -n helper src/a.c", "grep --line-number --context=2 helper src/a.c"])
def test_a_one_file_search_is_known_by_its_file(repo, cmd):
    assert g.single_bash_file(cmd, repo, repo) == "src/a.c"


@pytest.mark.parametrize("cmd", ["grep -c helper src/a.c", "grep -l -n helper src/a.c", "grep -n helper src/a.c src/b.c",
                                 "grep -A helper src/a.c", "grep -n helper src/a.c | head"])
def test_a_search_whose_output_is_not_line_text_of_one_file_is_not(repo, cmd):
    assert g.single_bash_file(cmd, repo, repo) is None


def test_matches_of_a_one_file_search_carry_the_file_and_the_graph_function(repo):
    out = subprocess.run(["grep", "-n", "-A2", "helper", "src/a.c"], cwd=repo, capture_output=True, text=True).stdout
    r = misses.parse_grep(out, names=["helper"], repo=repo, single_file="src/a.c")
    got = {m["at"]: m["in"] for m in r["matches"]}
    assert got["src/a.c:13"] == "caller_c" and got["src/a.c:2"] == "" and all(a.startswith("src/a.c:") for a in got)


def test_a_python_multi_line_header_is_named(repo):
    r = misses.parse_grep("m.py:5:    return helper(b)\n", names=["helper"], repo=repo)
    assert r["matches"][0]["in"] == "caller_py"


def test_a_file_changed_since_the_build_falls_back_to_the_text_scan(repo, tmp_path):
    import shutil
    copy = tmp_path / "copy"
    shutil.copytree(repo, copy)
    p = copy / "src" / "a.c"
    p.write_text("int top(void)\n{\n    return helper(1, 2);\n}\n" + C_A)
    os.utime(p, None)
    assert misses.graph_spans(copy, ["src/a.c"]) == {}
    r = misses.parse_grep("src/a.c:3:    return helper(1, 2);\n", names=["helper"], repo=copy)
    assert r["matches"][0]["in"] == misses.enclosing(copy, "src/a.c", 3, {})   # the text scan, not stale spans


def test_spans_pick_the_innermost_definition():
    spans = [(1, 20, "Outer"), (5, 10, "Outer.inner")]
    assert misses.enclosing_from_spans(spans, 7) == "Outer.inner"
    assert misses.enclosing_from_spans(spans, 15) == "Outer"
    assert misses.enclosing_from_spans(spans, 1) == "" and misses.enclosing_from_spans(spans, 30) == ""
