"""#260: a red suite records its failed tests; a test that passes when run again is flaky, not a failure of the change."""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
pb = importlib.import_module("policybench")


def _checkout(tmp_path, tests):
    w = tmp_path / "w"
    (w / ".venv" / "bin").mkdir(parents=True)
    py = w / ".venv" / "bin" / "python"              # a wrapper: a bare symlink would lose this interpreter's packages
    py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
    py.chmod(0o755)
    (w / "tests").mkdir()
    for name, body in tests.items():
        (w / "tests" / name).write_text(body)
    return w


FLAKY = ("from pathlib import Path\n\n\ndef test_flaky(tmp_path_factory):\n"
         "    mark = Path(__file__).with_suffix('.ran')\n"
         "    first = not mark.exists()\n    mark.write_text('x')\n    assert not first\n")


def test_a_test_that_fails_once_then_passes_is_flaky_and_the_suite_is_green(tmp_path):
    w = _checkout(tmp_path, {"test_ok.py": "def test_ok():\n    assert True\n", "test_flaky.py": FLAKY})
    r = pb.run_suite(w, timeout=120)
    assert r["suite_pass"] and r["suite_flaky"] == ["tests/test_flaky.py::test_flaky"] and r["suite_failed"] == []
    assert "1 failed" in r["suite_first"]


def test_a_test_that_always_fails_keeps_the_suite_red_with_its_id(tmp_path):
    w = _checkout(tmp_path, {"test_ok.py": "def test_ok():\n    assert True\n", "test_bad.py": "def test_bad():\n    assert False\n"})
    r = pb.run_suite(w, timeout=120)
    assert not r["suite_pass"] and r["suite_failed"] == ["tests/test_bad.py::test_bad"] and r["suite_flaky"] == []


def test_a_green_suite_is_run_once(tmp_path):
    w = _checkout(tmp_path, {"test_ok.py": "def test_ok():\n    assert True\n"})
    r = pb.run_suite(w, timeout=120)
    assert r["suite_pass"] and r["suite_failed"] == [] and "suite_first" not in r


def test_the_release_table_shows_flaky_runs_apart():
    rt = importlib.import_module("release_table")
    m = rt.summary([{"ok": True, "suite": True, "flaky": True, **{k: 0 for k in ("turns", "grep", "nav", "own", "sub", "ctx", "out", "cost", "wall", "answers", "answer_chars")}}])
    assert m["flaky"] == 1 and m["suite"] == 1


ORDER_A = "import builtins\n\n\ndef test_a():\n    builtins._poisoned = True\n"
ORDER_B = "import builtins\n\n\ndef test_b():\n    assert not hasattr(builtins, '_poisoned')\n"


def test_301_an_order_dependent_failure_that_passes_alone_keeps_the_suite_red(tmp_path):
    """Fails after test_a in every full run, passes on its own: not flaky, the suite is red (#301)."""
    w = _checkout(tmp_path, {"test_a.py": ORDER_A, "test_b.py": ORDER_B})
    r = pb.run_suite(w, timeout=120)
    assert not r["suite_pass"] and r["suite_failed"] == ["tests/test_b.py::test_b"] and r["suite_flaky"] == []
