#!/usr/bin/env python3
"""#366: the per-arm table of a batch from its rows (one scored row per run, with `first_call_tokens`).

  python bench/policy/arm_table.py bench/results/2026-11-20-user-policy-366/batch2-rows.jsonl [ARM,ARM,...]

Per ticket and pooled: first-call context and its difference to `none`, turns (the scored row's `turns`: model calls),
the context and cost per run, cost against `none` (pooled: the mean of the tickets' ratios), suite, hidden check and the
agents' devkb queries, and the cache tokens written per run (a cold prompt cache makes an arm look dearer).
"""
from __future__ import annotations

import json
import statistics as st
import sys

ARMS = ["none", "userpolicy", "userinit", "short", "outline", "inject", "main"]
HEAD = ("| Arm | n | First-call context k | Over none | Turns (med) | Context k (med) | Cost (mean) | Cost vs none | "
        "Cache written k (mean) | Suite | Hidden check | devkb queries |\n|---|---|---|---|---|---|---|---|---|---|---|---|")


def table(rows: list[dict], arms: list[str]) -> str:
    tickets = sorted({r["issue"] for r in rows}, key=lambda t: -int(t))
    cell = lambda t, a: [r for r in rows if r["issue"] == t and r["arm"] == a]
    mean = lambda xs, k: st.mean((r.get(k) or 0) for r in xs)
    out = []

    def line(a, xs, over, ratio):
        fc = [r["first_call_tokens"] for r in xs]
        span = f"{min(fc) / 1000:.1f}" if min(fc) == max(fc) else f"{min(fc) / 1000:.1f}-{max(fc) / 1000:.1f}"
        return (f"| {a} | {len(xs)} | {span} | {over} | {st.median(r['turns'] for r in xs):.0f} | "
                f"{st.median(r['ctx_tokens'] for r in xs) / 1000:.0f} | ${mean(xs, 'cost'):.3f} | {ratio} | "
                f"{mean(xs, 'cache_creation_tokens') / 1000:.0f} | {sum(bool(r['suite_pass']) for r in xs)}/{len(xs)} | "
                f"{sum(bool((r.get('acceptance') or {}).get('pass')) for r in xs)}/{len(xs)} | "
                f"{sum(r.get('devkb_queries') or 0 for r in xs)} |")

    for t in tickets:
        base = cell(t, "none")
        out += [f"\n#{t}\n", HEAD]
        for a in arms:
            xs = cell(t, a)
            if xs:
                over = "0" if a == "none" else f"{(mean(xs, 'first_call_tokens') - mean(base, 'first_call_tokens')) / 1000:+.1f}k"
                out.append(line(a, xs, over, f"{100 * (mean(xs, 'cost') / mean(base, 'cost') - 1):+.0f}%"))
    out += ["\nPooled (cost vs none: the mean of the tickets' ratios)\n", HEAD]
    for a in arms:
        xs = [r for r in rows if r["arm"] == a]
        if not xs:
            continue
        overs = [mean(cell(t, a), "first_call_tokens") - mean(cell(t, "none"), "first_call_tokens") for t in tickets]
        ratios = [mean(cell(t, a), "cost") / mean(cell(t, "none"), "cost") for t in tickets]
        lo, hi = f"{min(overs) / 1000:+.1f}", f"{max(overs) / 1000:+.1f}"
        over = "0" if a == "none" else f"{lo}k" if lo == hi else f"{lo} to {hi}k"
        out.append(line(a, xs, over, f"{100 * (st.mean(ratios) - 1):+.0f}%"))
    return "\n".join(out)


if __name__ == "__main__":
    rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
    print(table(rows, sys.argv[2].split(",") if len(sys.argv) > 2 else ARMS))
