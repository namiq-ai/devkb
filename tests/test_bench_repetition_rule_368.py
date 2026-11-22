"""#368: a result names a direction only at the number of runs that can show it. The table prints n and the cost's coefficient of variation per cell,
marks a per-ticket difference below the rule's n, and says when a release claim pools too few tickets."""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "policy"))
rt = importlib.import_module("release_table")


def row(arm, cost, ctx, run):
    return {"run": run, "arm": arm, "turns": 10, "calls": {"search": 3}, "ctx_tokens": ctx, "cost": cost, "seconds": 60,
            "acceptance": {"pass": True}, "suite_pass": True, "accept_sha256": "a"}


def cells(n, none_costs, main_costs, ticket="9"):
    rows = [row("nonekeep", none_costs[i % len(none_costs)], 100_000, f"{ticket}-n{i}") for i in range(n)]
    rows += [row("main", main_costs[i % len(main_costs)], 100_000, f"{ticket}-m{i}") for i in range(n)]
    return rows


def test_a_small_difference_at_three_runs_is_marked_below_n():
    out = rt.table([("9", cells(3, (0.30, 0.32, 0.34), (0.28, 0.33, 0.37)))])
    assert "(below n:" in out and "7 runs per arm" in out, out


def test_a_large_effect_at_three_runs_may_name_a_direction_but_says_how_few_runs_back_it():
    out = rt.table([("9", cells(3, (0.30, 0.32, 0.34), (0.60, 0.64, 0.68)))])
    assert "large effect, 3 runs per arm" in out and "(below n:" not in out, out


def test_at_the_rules_n_a_difference_is_read_without_a_mark():
    out = rt.table([("9", cells(rt.MIN_RUNS_PER_ARM, (0.30, 0.32, 0.34), (0.28, 0.33, 0.37)))])
    assert "(below n:" not in out and "large effect" not in out, out


def test_the_cell_prints_its_coefficient_of_variation():
    out = rt.table([("9", cells(3, (0.30, 0.32, 0.34), (0.28, 0.33, 0.37)))])
    assert ", CV 0.0" in out or ", CV 0.1" in out, out
    m = rt.summary([rt.per_run(row("main", c, 1, "x")) for c in (0.30, 0.32, 0.34)])
    assert abs(m["cost_cv"] - 0.0625) < 0.001                         # stdev 0.02 over mean 0.32
    assert rt.summary([rt.per_run(row("main", 0.3, 1, "x"))])["cost_cv"] is None, "one run has no spread"


def test_a_release_claim_pooling_too_few_tickets_says_so():
    one = rt.table([("9", cells(3, (0.30, 0.32, 0.34), (0.28, 0.33, 0.37)))])
    assert "below n for a release claim" in one and f"{rt.MIN_POOLED_TICKETS} tickets are needed, this has 1" in one
    pairs = [(str(t), cells(3, (0.30, 0.32, 0.34), (0.28, 0.33, 0.37), ticket=str(t))) for t in range(rt.MIN_POOLED_TICKETS)]
    assert "enough to pool" in rt.table(pairs)
