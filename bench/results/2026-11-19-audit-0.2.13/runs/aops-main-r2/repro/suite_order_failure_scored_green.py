"""run_suite's flaky rule scores a deterministically red suite green: a test that fails after another test's leftover state
(a change the agent made) passes when re-run alone, so it is called load-sensitive."""
import os, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "bench" / "policy"))
import policybench as pb  # noqa: E402

w = Path(tempfile.mkdtemp())
(w / ".venv" / "bin").mkdir(parents=True)
py = w / ".venv" / "bin" / "python"
py.write_text(f'#!/bin/sh\nexec {R}/.venv/bin/python "$@"\n')
py.chmod(0o755)
(w / "tests").mkdir()
(w / "tests" / "test_a.py").write_text("import os\n\ndef test_a():\n    os.environ['LEFTOVER'] = '1'   # what the agent's change leaves behind\n")
(w / "tests" / "test_b.py").write_text("import os\n\ndef test_b():\n    assert 'LEFTOVER' not in os.environ\n")
row = pb.run_suite(w)
print({k: row[k] for k in ("suite_pass", "suite_failed", "suite_flaky")})
full = os.popen(f"cd {w} && {py} -m pytest -q -p no:cacheprovider 2>&1 | tail -1").read().strip()
print("the full suite, run as a user would:", full)
print("expected: suite_pass False (the full suite is red every time, not only under load)")
sys.exit(1 if row["suite_pass"] else 0)
