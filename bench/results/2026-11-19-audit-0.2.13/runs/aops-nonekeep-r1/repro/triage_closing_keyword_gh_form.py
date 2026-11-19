"""clean_title (also the commit and PR title) and the PR summary strip closing keywords, but GitHub also closes on `Fixes GH-5`."""
import importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("triage", ROOT / "ops/triage/triage.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
cases = ["Fixes GH-5 crash on empty input", "Closes #5 crash", "Resolves octo/repo#5 crash"]
bad = False
for c in cases:
    out = t.clean_title(c)
    summ = t.CLOSING.sub("", t.sanitize(c))
    print(f"{c!r} -> title {out!r}, summary {summ!r}")
    if "GH-5" in out or "GH-5" in summ:
        bad = True
print("expected: no closing keyword survives in any form GitHub honours (#N, GH-N, owner/repo#N); actual: the GH-N form passes through")
sys.exit(1 if bad else 0)
