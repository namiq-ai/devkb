"""#304: a row whose transcript is not under bench/policy/runs uses its stored devkb_nav and devkb_selftest.
Black box on release_table.per_run."""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "bench" / "policy"))
rt = importlib.import_module("release_table")
rt.guard_rows = lambda session: []
row = {"run": "no-such-transcript-r1", "turns": 3, "calls": {}, "ctx_tokens": 1, "cost": 1.0, "seconds": 60, "suite_pass": True,
       "devkb_nav": 7, "devkb_selftest": 2}
p = rt.per_run(row)
out = {"stored_counts_used": (p["nav"], p["own"]) == (7, 2)}
out["pass"] = all(out.values())
print(json.dumps(out))
