"""`pack refactor` does not say Complete over a test list when a test file mentions the name with no call the graph resolved
(QB1 found it naming no covering test for 7 of 13 changes)."""
import subprocess

from devkb.cli import main


def repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "calc.py").write_text("def compute_total(items):\n    return sum(items)\n")
    (tmp_path / "pkg" / "use.py").write_text("from pkg.calc import compute_total\n\n\ndef report(xs):\n    return compute_total(xs)\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_use.py").write_text("from pkg.use import report\n\n\ndef test_report():\n    assert report([1, 2]) == 3\n")
    # a test that reaches the function through a helper object the graph cannot type
    (tmp_path / "tests" / "test_indirect.py").write_text(
        "from helpers import make\n\n\ndef test_total():\n    api = make()\n    assert api.compute_total([1, 2]) == 3\n")
    (tmp_path / "tests" / "test_comment.py").write_text("# compute_total is covered elsewhere\n\n\ndef test_x():\n    assert True\n")
    (tmp_path / "helpers.py").write_text("def make():\n    return object()\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    assert main(["build", "--project", str(tmp_path)]) == 0


def pack(tmp_path, capsys, name):
    capsys.readouterr()
    assert main(["pack", "--project", str(tmp_path), "refactor", name]) == 0
    return capsys.readouterr().out


def test_a_test_that_mentions_the_name_with_no_resolved_call_is_named_and_the_verdict_is_incomplete(tmp_path, capsys):
    repo(tmp_path)
    out = pack(tmp_path, capsys, "compute_total")
    assert "## Test files among them (0)" in out                        # direct callers only: test_use.py reaches it through `report`
    sec = out.split("## Test files that mention it with no call the graph resolved")[1].split("## Coverage")[0]
    assert "tests/test_indirect.py:6" in sec and "test_comment.py" not in sec and "test_use.py" not in sec    # a comment is not a mention
    assert "Incomplete for tests: 1 test file(s) mention `compute_total`" in out.split("## Coverage")[1]


def test_no_section_and_the_old_verdict_when_nothing_mentions_it(tmp_path, capsys):
    repo(tmp_path)
    (tmp_path / "tests" / "test_indirect.py").write_text("def test_total():\n    assert True\n")
    out = pack(tmp_path, capsys, "compute_total")
    assert "mention it with no call" not in out and "Incomplete for tests" not in out


def test_a_name_many_definitions_share_is_not_looked_for_in_the_tests(tmp_path, capsys):
    """`resolve` is defined in many places and `Path.resolve()` is in every test suite: a mention of it says nothing."""
    (tmp_path / "pkg").mkdir()
    for i in range(5):
        (tmp_path / "pkg" / f"m{i}.py").write_text("def resolve(x):\n    return x\n")
    (tmp_path / "pkg" / "one.py").write_text("def unique_thing(x):\n    return x\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("from pathlib import Path\n\n\ndef test_a():\n    assert Path('.').resolve()\n    assert helper.unique_thing(1)\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    assert main(["build", "--project", str(tmp_path)]) == 0
    assert "mention it with no call" not in pack(tmp_path, capsys, "pkg/m0.py::resolve")                 # five other `resolve`
    assert "tests/test_a.py:6" in pack(tmp_path, capsys, "unique_thing")                                 # a unique name is


def test_the_guardrails_scope_filter_keeps_the_mention_section_apart_from_the_test_list():
    """`filter_pack` counts the files of a section by its heading; the mention section also starts with `## Test files`."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("g", Path(__file__).resolve().parents[1] / "scripts" / "devkb_guardrail.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    pack = ("## Files with a direct caller (2, tests included)\n- `pkg/use.py` — `x`\n- `tests/test_b.py` — `y`\n\n"
            "## Test files among them (1)\n- `tests/test_b.py`\n\n"
            "## Test files that mention it with no call the graph resolved (2)\n- `tests/test_a.py:3`\n- `tests/test_b.py:9`\n")
    out, _kept = g.filter_pack(pack, ["tests"])
    assert "## Test files among them (1)" in out                       # the count follows the listed files only, not the mention lines
    assert "- `tests/test_a.py:3`" in out and "- `pkg/use.py`" not in out
