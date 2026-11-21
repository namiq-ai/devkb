#!/usr/bin/env python3
"""QB1, original against shipped: the benchmark as first measured (each snapshot's own devkb) against the pack as shipped on this branch,
with what each costs an agent to read. Reads the results `qb1_tests.py score` wrote (one pass over every snapshot), so the arms were
scored on the same items.

  original   `pack file` and `pack refactor` of the snapshot's own devkb
  shipped    this checkout's `pack file` (direct marking) and `pack refactor` (tests that mention the function, Incomplete for tests)
  import / grep   the two baselines

Sets: tuning = the 3 snapshots the changes were designed against; held-out = every later snapshot, never used for design.
Cost: characters of the packs an agent would ask for (one `pack file` per changed file, one `pack refactor` per changed function), at
4 characters a token. `found per 1k tokens` = covering test files named per 1000 tokens of pack read.

  python bench/quality/qb1_compare.py [--tuning SHA,SHA,SHA]"""
import json
import random
import statistics as st
import sys
from pathlib import Path

CACHE = Path.home() / ".cache" / "devkb" / "qb1"
TUNING = ("632f8d0", "ea9d037", "215c505")
ARMS = (("original", "original pack"), ("shipped", "shipped pack"), ("import", "import search"), ("grep", "grep of names"))


def boot(xs, n=3000, seed=5):
    rnd = random.Random(seed)
    m = sorted(st.mean(rnd.choices(xs, k=len(xs))) for _ in range(n))
    return m[int(.05 * n)], m[int(.95 * n) - 1]


def table(rows: list[dict], label: str) -> None:
    cov = [r for r in rows if r["covered"]]
    if not cov:
        return
    print(f"\n{label}: {len(cov)} scored items from {len({r['snapshot'] for r in cov})} snapshots\n")
    print("| arm | files named | recall | precision | pack chars per item | tokens per item | found per 1k tokens |\n|---|---|---|---|---|---|---|")
    for a, name in ARMS:
        rec = [r[a]["rec_all"] for r in cov]
        pr = [r[a]["prec"] for r in cov if r[a]["prec"] is not None]
        lo, hi = boot(rec)
        ch = [r["chars"][a] for r in cov] if a in ("original", "shipped") else None
        found = [r[a]["rec_all"] * r["truth"] for r in cov]
        cost = f"{st.mean(ch):.0f} | {st.mean(ch) / 4:.0f} | {1000 * sum(found) / (sum(ch) / 4):.1f}" if ch else "- | - | -"
        print(f"| {name} | {st.median(r[a]['n'] for r in cov):.0f} | {st.mean(rec):.2f} ({lo:.2f}-{hi:.2f}) | {st.mean(pr):.2f} | {cost} |")
    print("\nPaired recall, 90% over items: " + "; ".join(
        f"{x} - {y} {st.mean(d):+.2f} ({boot(d)[0]:+.2f} to {boot(d)[1]:+.2f})"
        for x, y in (("shipped", "original"), ("shipped", "import"), ("shipped", "grep"))
        for d in [[r[x]["rec_all"] - r[y]["rec_all"] for r in cov]]))
    dc = [r["chars"]["shipped"] - r["chars"]["original"] for r in cov]
    print(f"Cost of the shipped changes: {st.mean(dc):+.0f} characters per item ({st.mean(dc) / 4:+.0f} tokens), "
          f"{100 * st.mean(dc) / st.mean(r['chars']['original'] for r in cov):+.0f}% on the original packs")


def main() -> None:
    tuning = {s[:7] for s in (sys.argv[sys.argv.index("--tuning") + 1].split(",") if "--tuning" in sys.argv else TUNING)}      # 7 characters, however a sha was typed
    rows = json.loads((CACHE / "qb1-results.json").read_text())
    snaps = sorted({r["snapshot"][:7] for r in rows})
    for r in rows:
        r["snapshot"] = r["snapshot"][:7]
    print("per snapshot (items; recall original / shipped / import / grep):")
    for s in snaps:
        c = [r for r in rows if r["snapshot"] == s and r["covered"]]
        if c:
            print(f"  {s} {'tuning' if s in tuning else 'held-out'} {len(c)}: " + " / ".join(f"{st.mean(r[a]['rec_all'] for r in c):.2f}" for a, _ in ARMS))
    table([r for r in rows if r["snapshot"] in tuning], "tuning (designed against)")
    table([r for r in rows if r["snapshot"] not in tuning], "HELD-OUT (never used for design)")
    table(rows, "ALL")


if __name__ == "__main__":
    main()
