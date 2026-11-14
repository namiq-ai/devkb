#!/usr/bin/env python3
"""Aggregate lifecycle benchmark results into a per-stage table (ODSF-308).

  python3 devkb/bench/report.py RESULTS.jsonl [--json]

For each stage and arm: valid runs, graph adoption (share of runs that called a graph tool), median cost,
turns, tokens of tool output returned to the model (bytes), fresh tokens, seconds, and mean correctness.
Invalid runs (no parsable answer) are counted and excluded from medians; they are never scored as correct.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict

ARMS = ("plain", "graph", "graph_forced")


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def pct(a, b):
    return None if a is None or not b else round((a - b) / b * 100)


def aggregate(rows: list[dict]) -> dict:
    cells: dict = defaultdict(list)
    for r in rows:
        cells[(r["stage"], r["arm"])].append(r)
    out: dict = {}
    for (stage, arm), rs in sorted(cells.items()):
        valid = [r for r in rs if r["valid"]]
        out.setdefault(stage, {})[arm] = {
            "runs": len(rs), "valid": len(valid),
            "adoption": round(sum(1 for r in valid if r["graph_calls"] > 0) / len(valid), 2) if valid else None,
            "cost": med([r["cost"] for r in valid]), "turns": med([r["turns"] for r in valid]),
            "bytes": med([r["result_bytes"] for r in valid]), "fresh": med([r["fresh"] for r in valid]),
            "secs": med([r["secs"] for r in valid]),
            "score": round(statistics.mean(r["score"] for r in valid), 2) if valid else None}
    return out


def render(agg: dict) -> str:
    lines = ["| Stage | Arm | Valid | Used graph | Median cost | Turns | Tool output (bytes) | Correct | Cost vs plain | Bytes vs plain |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for stage, arms in agg.items():
        base = arms.get("plain", {})
        for arm in ARMS:
            c = arms.get(arm)
            if not c:
                continue
            used = "" if c["adoption"] is None else "{:.0%}".format(c["adoption"])
            d_cost = "" if arm == "plain" else "{}%".format(pct(c["cost"], base.get("cost")))
            d_bytes = "" if arm == "plain" else "{}%".format(pct(c["bytes"], base.get("bytes")))
            lines.append("| {} | {} | {}/{} | {} | ${:.3f} | {:.0f} | {:.0f} | {:.2f} | {} | {} |".format(
                stage, arm, c["valid"], c["runs"], used, c["cost"], c["turns"], c["bytes"], c["score"], d_cost, d_bytes))
    totals = {a: sum(arms[a]["cost"] for arms in agg.values() if arms.get(a) and arms[a]["cost"] is not None) for a in ARMS}
    lines.append("")
    lines.append("Sum of stage median costs: " + ", ".join(f"{a} ${v:.2f}" for a, v in totals.items() if v))
    return "\n".join(lines)


def main() -> int:
    rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
    agg = aggregate(rows)
    print(json.dumps(agg, indent=1) if "--json" in sys.argv else render(agg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
