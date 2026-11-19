"""A run refused for a red base (#221) is attempted again once the base is green; today its `end` file makes every later batch skip it."""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
import policybench as pb

tmp = Path(tempfile.mkdtemp())
pb.B = tmp
out = tmp / "runs" / "p9-before-r1"
out.mkdir(parents=True)
(out / "end").write_text('{"exit": "base-red", "seconds": 0, "error": "suite red"}')
attempted = []


def tmpl(arm):
    attempted.append(arm)
    raise RuntimeError("stop here: setup was attempted")


pb.template_for = tmpl
res = pb._run_one("9", "before", 1)
print("result:", res, "| setup attempted:", bool(attempted))
print("expected: like exit=error, a base-red run is set up again (the base may be fixed); actual: skipped for good, so the "
      "arm has fewer runs than its siblings and the table compares unequal arms")
sys.exit(0 if attempted else 1)
