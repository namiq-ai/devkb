"""#301: a suite that fails the same way on two full runs is red, even when the failed test passes alone; a test that
fails once and passes in the second full run is still flaky. Black box on policybench.run_suite."""
import importlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "bench" / "policy"))
pb = importlib.import_module("policybench")


def checkout(td, tests):
    w = Path(td) / "w"
    (w / ".venv" / "bin").mkdir(parents=True)
    py = w / ".venv" / "bin" / "python"
    py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
    py.chmod(0o755)
    (w / "tests").mkdir()
    for n, b in tests.items():
        (w / "tests" / n).write_text(b)
    return w


A = "import builtins\n\n\ndef test_a():\n    builtins._poisoned = True\n"
B = "import builtins\n\n\ndef test_b():\n    assert not hasattr(builtins, '_poisoned')\n"
FLAKY = ("from pathlib import Path\n\n\ndef test_flaky():\n    m = Path(__file__).with_suffix('.ran')\n"
         "    first = not m.exists()\n    m.write_text('x')\n    assert not first\n")
out = {}
with tempfile.TemporaryDirectory() as td:
    r = pb.run_suite(checkout(td, {"test_a.py": A, "test_b.py": B}), timeout=300)
    out["order_dependent_is_red"] = (not r["suite_pass"]) and r["suite_failed"] == ["tests/test_b.py::test_b"]
with tempfile.TemporaryDirectory() as td:
    r = pb.run_suite(checkout(td, {"test_ok.py": "def test_ok():\n    pass\n", "test_flaky.py": FLAKY}), timeout=300)
    out["once_then_green_is_flaky"] = bool(r["suite_pass"]) and r["suite_flaky"] == ["tests/test_flaky.py::test_flaky"]
out["pass"] = all(out.values())
print(json.dumps(out))
