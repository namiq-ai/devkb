#!/usr/bin/env python3
"""ADDENDUM-1 S1: the 2x2 ablation (graph content G0/G1 x coverage C0/C1, core arm) against the shared plain baseline.

  python3 analyze_ablation.py ABLATION_DIR --out ablation.json

Per cell: cost effect against plain (1 - sum_t mean cell / sum_t mean plain) and mean score. Main effect of content =
mean over C of (effect G1 - effect G0); of coverage = mean over G of (C1 - C0); interaction = (G1C1 - G0C1) -
(G1C0 - G0C0). 95% bootstrap intervals resample runs within task (10,000 draws, seed 1). Descriptive only.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
from pathlib import Path

CELLS = ("G0C0", "G0C1", "G1C0", "G1C1")
DRAWS = 10_000


def load(path: Path) -> dict[str, list[dict]]:
    by = collections.defaultdict(list)
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            r["score"] = r.get("score", 0.0) if r.get("valid") else 0.0
            by[r["task"]].append(r)
    return by


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    d = Path(ns.dir)
    pick = lambda c: d / c / "runs.jsonl" if (d / c / "runs.jsonl").exists() else d / c / f"{c}.jsonl"  # D3 re-run naming
    plain = load(pick("PLAIN"))
    cells = {c: load(pick(c)) for c in CELLS}
    tasks = sorted(t for t in plain if all(t in cells[c] for c in CELLS))

    def stats(sample_plain, sample_cells):
        base = sum(statistics.mean(r["cost"] for r in sample_plain[t]) for t in tasks)
        eff = {c: 1 - sum(statistics.mean(r["cost"] for r in sample_cells[c][t]) for t in tasks) / base for c in CELLS}
        score = {c: statistics.mean(statistics.mean(r["score"] for r in sample_cells[c][t]) for t in tasks) for c in CELLS}
        main_content = ((eff["G1C0"] - eff["G0C0"]) + (eff["G1C1"] - eff["G0C1"])) / 2
        main_coverage = ((eff["G0C1"] - eff["G0C0"]) + (eff["G1C1"] - eff["G1C0"])) / 2
        interaction = (eff["G1C1"] - eff["G0C1"]) - (eff["G1C0"] - eff["G0C0"])
        return eff, score, {"content": main_content, "coverage": main_coverage, "interaction": interaction}

    eff, score, effects = stats(plain, cells)
    rnd = random.Random(1)
    draws = collections.defaultdict(list)
    for _ in range(DRAWS):
        sp = {t: [rnd.choice(plain[t]) for _ in plain[t]] for t in tasks}
        sc = {c: {t: [rnd.choice(cells[c][t]) for _ in cells[c][t]] for t in tasks} for c in CELLS}
        e, s, f = stats(sp, sc)
        for k, v in {**e, **{f"effect_{k}": v for k, v in f.items()}, **{f"score_{k}": v for k, v in s.items()}}.items():
            draws[k].append(v)

    def ci(k):
        xs = sorted(draws[k])
        return [round(xs[int(DRAWS * .025)], 4), round(xs[int(DRAWS * .975)], 4)]

    out = {"tasks": len(tasks), "runs": sum(len(v) for v in plain.values()) + sum(len(v) for c in CELLS for v in cells[c].values()),
           "cost_usd": round(sum(r["cost"] or 0 for v in plain.values() for r in v) + sum(r["cost"] or 0 for c in CELLS for v in cells[c].values() for r in v), 2),
           "plain_score": round(statistics.mean(statistics.mean(r["score"] for r in plain[t]) for t in tasks), 4),
           "cells": {c: {"saved": round(eff[c], 4), "ci": ci(c), "score": round(score[c], 4), "score_ci": ci(f"score_{c}"),
                         "median_turns": statistics.median(r.get("turns") or 0 for t in tasks for r in cells[c][t])} for c in CELLS},
           "effects": {k: {"value": round(v, 4), "ci": ci(f"effect_{k}")} for k, v in effects.items()}}
    Path(ns.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
