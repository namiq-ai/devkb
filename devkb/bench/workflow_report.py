#!/usr/bin/env python3
"""Summarise workflow benchmark rows: per task kind and arm, median cost, turns, tool-result bytes, mean score, and the
cost saved against plain with a bootstrap 95% interval (resampling runs within each task).

  python3 workflow_report.py results.jsonl
"""
from __future__ import annotations

import collections
import json
import random
import statistics
import sys


def boot(rows_by_task: dict, arm: str, n: int = 4000) -> tuple[float, float, float]:
    """Cost saved by `arm` against plain: 1 - sum(mean arm cost per task) / sum(mean plain cost per task)."""
    rnd = random.Random(1)

    def saved(sample):
        a = sum(statistics.mean(s[arm]) for s in sample.values())
        p = sum(statistics.mean(s["plain"]) for s in sample.values())
        return 1 - a / p

    point = saved(rows_by_task)
    draws = []
    for _ in range(n):
        draws.append(saved({t: {k: [rnd.choice(v) for _ in v] for k, v in s.items()} for t, s in rows_by_task.items()}))
    draws.sort()
    return point, draws[int(n * 0.025)], draws[int(n * 0.975)]


def main() -> int:
    rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
    print(f"{len(rows)} runs, {sum(r['valid'] for r in rows)} valid, total ${sum(r['cost'] or 0 for r in rows):.2f}\n")
    kinds = sorted({r["kind"] for r in rows}) + ["ALL"]
    print(f"{'kind':9} {'arm':9} {'n':>2} {'cost$':>7} {'turns':>5} {'bytes':>7} {'score':>5} {'graph%':>6}  saved vs plain [95%]  tools used")
    for kind in kinds:
        sel = [r for r in rows if kind == "ALL" or r["kind"] == kind]
        by_task: dict = collections.defaultdict(lambda: collections.defaultdict(list))
        for r in sel:
            if r["cost"] is not None:
                by_task[r["task"]][r["arm"]].append(r["cost"])
        arms = [a for a in ("plain", "core", "workflow", "lean", "pack") if any(r["arm"] == a for r in sel)]
        by_task = {t: s for t, s in by_task.items() if all(s.get(a) for a in arms)}
        for arm in arms:
            a = [r for r in sel if r["arm"] == arm]
            if not a:
                continue
            med = lambda k: statistics.median([r[k] or 0 for r in a])  # noqa: E731
            used = collections.Counter(t for r in a for t in r.get("graph_tools", []))
            saved = ""
            if arm != "plain" and by_task:
                p, lo, hi = boot(by_task, arm)
                saved = f"{p:+.0%} [{lo:+.0%}, {hi:+.0%}]"
            print(f"{kind:9} {arm:9} {len(a):2} {med('cost'):7.3f} {med('turns'):5.0f} {med('result_bytes'):7.0f} "
                  f"{statistics.mean(r['score'] for r in a):5.2f} {sum(r['graph_calls'] > 0 for r in a) / len(a):6.0%}  {saved:22} "
                  f"{', '.join(f'{k}×{v}' for k, v in used.most_common(4))}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
