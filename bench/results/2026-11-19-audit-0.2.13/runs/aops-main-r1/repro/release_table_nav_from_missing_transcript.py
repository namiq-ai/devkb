"""release_table.per_run recounts devkb navigation / self-tests / replaced searches from bench/policy/runs/<run>/stream.jsonl
and returns 0 when that file is absent, ignoring the devkb_nav / devkb_selftest the scored row already holds (remeasure.py
accepts --runs DIRs because transcripts live elsewhere). The table then reports no devkb use for a run that used it."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import release_table as rt  # noqa: E402
rt.GUARD_LOG = Path("/nonexistent")
row = {"run": "p999-main-r1-not-on-this-disk", "arm": "main", "turns": 30, "calls": {"search": 4}, "ctx_tokens": 100000,
       "out_tokens": 5000, "cost": 1.0, "seconds": 600, "suite_pass": True, "acceptance": {"pass": True},
       "devkb_nav": 7, "devkb_selftest": 2}
m = rt.per_run(row)
print("row says devkb_nav=7 devkb_selftest=2; the table uses nav =", m["nav"], "own =", m["own"])
print("expected: the stored counts are used when the transcript is not under bench/policy/runs")
sys.exit(1 if (m["nav"], m["own"]) != (7, 2) else 0)
