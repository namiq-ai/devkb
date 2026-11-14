#!/usr/bin/env python3
"""ADDENDUM-1 S2: process-layer study. H6: pack costs less than plain, quality non-inferior (margin 0.05); one-sided
Wilcoxon over per-task mean cost differences; reported separately from H1-H5. Core is reported descriptively.

  python3 analyze_process.py runs/process/A/A.jsonl runs/process/B/B.jsonl --out results-process.json
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import analyze as an


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    rows = an.load(ns.runs)
    rnd = random.Random(1)
    c = an.cells(rows)
    arms = [a for a in ("plain", "core", "pack") if any(r["arm"] == a for r in rows)]
    res = {"runs": len(rows), "cost_usd": round(sum(r["cost"] for r in rows), 2), "tasks": len(c),
           "invalid": sum(1 for r in rows if not r.get("valid")),
           "describe": {a: an.describe(rows, a) for a in arms},
           "pooled": {a: {"cost": an.cost_effect(c, a, rnd), "quality": an.quality(c, a, rnd)} for a in arms if a != "plain"},
           "by_kind": {}}
    for kind in sorted({r["kind"] for r in rows}):
        sub = an.cells([r for r in rows if r["kind"] == kind])
        res["by_kind"][kind] = {a: {"cost": an.cost_effect(sub, a, rnd), "quality": an.quality(sub, a, rnd)} for a in arms if a != "plain"}
    h6 = res["pooled"].get("pack")
    if h6:
        res["H6"] = {"saved": h6["cost"]["saved"], "ci": [h6["cost"]["lo"], h6["cost"]["hi"]], "p": h6["cost"]["p_wilcoxon"],
                     "quality_diff": h6["quality"]["diff"], "non_inferior": h6["quality"]["non_inferior"],
                     "supported": h6["cost"]["p_wilcoxon"] < 0.05 and h6["quality"]["non_inferior"]}
    Path(ns.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("runs", "tasks", "invalid", "cost_usd")}), json.dumps(res.get("H6")))
    for k, v in res["by_kind"].items():
        for a, x in v.items():
            print(k, a, "saved", x["cost"]["saved"], [x["cost"]["lo"], x["cost"]["hi"]], "quality diff", x["quality"]["diff"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
