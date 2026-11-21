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
