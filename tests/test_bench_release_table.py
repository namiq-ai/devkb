"""#222, #223: the release table shows spread, marks noise, gives an interval, and refuses mixed hidden checks."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "policy"))
rt = importlib.import_module("release_table")


def row(arm, cost, ctx, run="r", sha="a"):
    return {"run": run, "arm": arm, "turns": 10, "calls": {"search": 3}, "ctx_tokens": ctx, "cost": cost, "seconds": 60,
            "acceptance": {"pass": True}, "suite_pass": True, "accept_sha256": sha}


def test_overlapping_ranges_are_within_noise_and_separate_ones_are_not():
    a = rt.summary([rt.per_run(row("main", c, 1000)) for c in (0.5, 0.7, 0.9)])
    b = rt.summary([rt.per_run(row("nonekeep", c, 1000)) for c in (0.6, 0.8, 1.0)])
    far = rt.summary([rt.per_run(row("main", c, 1000)) for c in (0.1, 0.15, 0.2)])
    assert rt.within_noise(a, b, "cost") and not rt.within_noise(far, b, "cost")


def test_the_interval_contains_a_constant_difference_and_is_ordered():
    lo, hi = rt.bootstrap([-0.1, -0.1, -0.1])
    assert lo == hi == pytest.approx(-0.1)
    lo, hi = rt.bootstrap([-0.3, 0.0, 0.1, -0.2, 0.05])
    assert lo <= hi


def test_runs_scored_by_different_checks_are_refused():
    rows = [row("main", 0.5, 1000, sha="a"), row("nonekeep", 0.6, 1000, sha="b")]
    with pytest.raises(SystemExit, match="#7: runs scored by 2 versions"):
        rt.table([("7", rows)])
    assert "Mixed hidden-check versions" in rt.table([("7", rows)], allow_mixed=True)


def test_the_table_prints_ranges_and_marks_noise():
    rows = [row("nonekeep", c, 1000 * c, run=f"n{c}") for c in (0.6, 0.8, 1.0)] + \
           [row("main", c, 1000 * c, run=f"m{c}") for c in (0.5, 0.7, 0.9)]
    out = rt.table([("9", rows)])
    assert "0.70 (0.50–0.90)" in out and "(within noise)" in out and "90% interval" in out
