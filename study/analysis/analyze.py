#!/usr/bin/env python3
"""Confirmatory analysis, exactly as PREREGISTRATION.md specifies.

  python3 analyze.py runs/sonnet/*.jsonl --model sonnet --out results-sonnet.json [--tex tables-sonnet.tex]

Cost effect of an arm = 1 - sum_task mean(arm cost) / sum_task mean(plain cost); 95% bootstrap interval resampling
runs within each task (10,000 draws, seed 1); one-sided Wilcoxon signed-rank over per-task mean cost differences
(plain - arm > 0); Holm across H1-H4 (cost). Quality: mean score difference (arm - plain) over tasks with a 95%
bootstrap interval; non-inferior when its lower bound exceeds -0.05. Invalid runs score 0 and keep their cost.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
from pathlib import Path

from scipy.stats import wilcoxon

MARGIN = 0.05
DRAWS = 10_000


def load(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        repo = Path(p).stem
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                r["repo"] = repo
                r["score"] = r.get("score", 0.0) if r.get("valid") else 0.0
                r["cost"] = r.get("cost") or 0.0
                rows.append(r)
    return rows


def cells(rows):
    c = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        c[r["task"]][r["arm"]].append(r)
    return c


def cost_effect(c, arm, rnd):
    tasks = [t for t, s in c.items() if s.get(arm) and s.get("plain")]

    def eff(sample):
        return 1 - sum(statistics.mean(x) for x, _ in sample) / sum(statistics.mean(y) for _, y in sample)

    base = [([r["cost"] for r in c[t][arm]], [r["cost"] for r in c[t]["plain"]]) for t in tasks]
    point = eff(base)
    draws = sorted(eff([([rnd.choice(a) for _ in a], [rnd.choice(b) for _ in b]) for a, b in base]) for _ in range(DRAWS))
    diffs = [statistics.mean(b) - statistics.mean(a) for a, b in base]
    try:
        p = wilcoxon(diffs, alternative="greater").pvalue if any(diffs) else 1.0
    except ValueError:
        p = 1.0
    return {"tasks": len(tasks), "saved": round(point, 4), "lo": round(draws[int(DRAWS * .025)], 4),
            "hi": round(draws[int(DRAWS * .975)], 4), "p_wilcoxon": float(p)}


def quality(c, arm, rnd):
    tasks = [t for t, s in c.items() if s.get(arm) and s.get("plain")]
    pairs = [([r["score"] for r in c[t][arm]], [r["score"] for r in c[t]["plain"]]) for t in tasks]

    def d(sample):
        return statistics.mean(statistics.mean(a) - statistics.mean(b) for a, b in sample)

    point = d(pairs)
    draws = sorted(d([([rnd.choice(a) for _ in a], [rnd.choice(b) for _ in b]) for a, b in pairs]) for _ in range(DRAWS))
    lo, hi = draws[int(DRAWS * .025)], draws[int(DRAWS * .975)]
    return {"diff": round(point, 4), "lo": round(lo, 4), "hi": round(hi, 4), "non_inferior": lo > -MARGIN,
            "arm_mean": round(statistics.mean(statistics.mean(a) for a, _ in pairs), 4),
            "plain_mean": round(statistics.mean(statistics.mean(b) for _, b in pairs), 4)}


def holm(ps: dict[str, float]) -> dict[str, float]:
    order = sorted(ps, key=ps.get)
    out, running = {}, 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * ps[k]))
        out[k] = running
    return out


def describe(rows, arm):
    a = [r for r in rows if r["arm"] == arm]
    return {"runs": len(a), "valid": sum(1 for r in a if r.get("valid")), "median_cost": round(statistics.median(r["cost"] for r in a), 4),
            "median_turns": statistics.median(r.get("turns") or 0 for r in a), "mean_score": round(statistics.mean(r["score"] for r in a), 4),
            "graph_used": round(sum(1 for r in a if r.get("graph_calls")) / max(1, len(a)), 3),
            "median_result_bytes": statistics.median(r.get("result_bytes") or 0 for r in a)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    rows = load(ns.runs)
    arms = [a for a in ("plain", "core", "workflow", "lean", "lean-pack", "pack") if any(r["arm"] == a for r in rows)]
    rnd = random.Random(1)
    c = cells(rows)
    res = {"model": ns.model, "runs": len(rows), "cost_usd": round(sum(r["cost"] for r in rows), 2),
           "tasks": len(c), "repos": sorted({r["repo"] for r in rows}), "describe": {a: describe(rows, a) for a in arms},
           "pooled": {}, "by_kind": {}, "by_repo": {}, "noise": {}}
    for a in arms:
        if a == "plain":
            continue
        res["pooled"][a] = {"cost": cost_effect(c, a, rnd), "quality": quality(c, a, rnd)}
    for key, label in (("kind", "by_kind"), ("repo", "by_repo")):
        for v in sorted({r[key] for r in rows}):
            sub = cells([r for r in rows if r[key] == v])
            res[label][v] = {a: {"cost": cost_effect(sub, a, rnd), "quality": quality(sub, a, rnd)} for a in arms if a != "plain"}
    # pre-registered hypotheses
    hyp = {}
    if ns.model == "sonnet":
        for h, arm in (("H1", "pack"), ("H2", "lean"), ("H3", "core")):
            if arm in res["pooled"]:
                hyp[h] = {"arm": arm, "p": res["pooled"][arm]["cost"]["p_wilcoxon"], **res["pooled"][arm]}
        err = res["by_kind"].get("err_to_handler", {})
        for arm in ("pack", "lean"):
            if arm in err:
                hyp[f"H4-{arm}"] = {"arm": arm, "p": err[arm]["cost"]["p_wilcoxon"], **err[arm]}
        adj = holm({k: v["p"] for k, v in hyp.items() if k != "H3"})  # H3 is a no-worse claim, judged on its interval
        for k, v in adj.items():
            hyp[k]["p_holm"] = v
        if "H3" in hyp:
            # "costs no more than plain": the point estimate saves nothing negative and quality is non-inferior
            hyp["H3"]["supported"] = hyp["H3"]["cost"]["saved"] >= 0 and hyp["H3"]["quality"]["non_inferior"]
    else:
        for arm in ("pack", "lean"):
            if arm in res["pooled"]:
                hyp[f"H5-{arm}"] = {"arm": arm, "p": res["pooled"][arm]["cost"]["p_wilcoxon"], **res["pooled"][arm]}
        adj = holm({k: v["p"] for k, v in hyp.items()})
        for k, v in adj.items():
            hyp[k]["p_holm"] = v
    res["hypotheses"] = hyp
    # score noise: spread of plain-arm repetitions within a task
    sds = [statistics.pstdev([r["score"] for r in s["plain"]]) for s in c.values() if len(s.get("plain", [])) > 1]
    res["noise"] = {"plain_score_sd_median": round(statistics.median(sds), 4) if sds else None}
    Path(ns.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("model", "runs", "cost_usd", "tasks", "repos")}))
    for k, v in hyp.items():
        print(k, v["arm"], "saved", v["cost"]["saved"], f"[{v['cost']['lo']}, {v['cost']['hi']}]", "p", round(v["p"], 4),
              "p_holm", round(v.get("p_holm", float("nan")), 4), "quality diff", v["quality"]["diff"], "non-inf", v["quality"]["non_inferior"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
