"""#221: a run refused for a red base is recorded as exit "base-red" and never run again: _run_one only re-runs
"error". After the base is fixed, `policybench.py run` prints "skip" for it, so the arm stays empty unless
someone deletes runs/<tag>/end by hand."""
import json, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import policybench as pb  # noqa: E402
tmp = Path(tempfile.mkdtemp())
pb.B = tmp
out = tmp / "runs" / "p7-main-r1"
out.mkdir(parents=True)
(out / "end").write_text(json.dumps({"exit": "base-red", "seconds": 0, "error": "suite red"}))
res = pb._run_one("7", "main", 1)
print(res)
print("expected: a base-red run is run again (as an error run is), not skipped")
sys.exit(1 if res.startswith("skip") else 0)
