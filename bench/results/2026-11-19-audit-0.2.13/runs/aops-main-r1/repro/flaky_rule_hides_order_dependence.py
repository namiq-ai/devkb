"""#260: a failed test that passes when re-run alone is called flaky and the suite counts as green. A test the agent's
change breaks only when it runs after the agent's new test (shared state) also passes alone, so a red suite
caused by the agent is scored green."""
import os, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import policybench as pb  # noqa: E402
w = Path(tempfile.mkdtemp())
(w / ".venv" / "bin").mkdir(parents=True)
py = w / ".venv" / "bin" / "python"
py.write_text(f'#!/bin/sh\nexec {root / ".venv" / "bin" / "python"} "$@"\n'); py.chmod(0o755)
(w / "tests").mkdir()
(w / "tests" / "test_a_new.py").write_text("import os\ndef test_new():\n    import builtins; builtins._leak = 1\n")   # the agent's test leaks in-process state
(w / "tests" / "test_b_old.py").write_text("import builtins\ndef test_old():\n    assert not hasattr(builtins, '_leak')\n")
r = pb.run_suite(w)
print({k: r[k] for k in ("suite_pass", "suite_failed", "suite_flaky", "suite")}, r.get("suite_first"))
print("expected: suite_pass False, the order-dependent failure is the change's, not flakiness")
sys.exit(1 if r["suite_pass"] else 0)
