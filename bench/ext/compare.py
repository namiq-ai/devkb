#!/usr/bin/env python3
"""Compare the arms of an external-repository run (bench/ext/extbench.py) on quality and efficiency.

Quality: the hidden check (the fix's own tests plus every older test, built from the agent's tree), per ticket and overall.
Efficiency: turns, cost, context and output tokens, wall time, and what the agent did (search calls, read-type calls, devkb calls, `pack` calls).
Paired differences between arms use a 90% interval from resampling the runs within each ticket and averaging the tickets with equal
weight (release_table.strat_boot), the same method as the devkb-repository tables.

  python bench/ext/compare.py [--arms none,orig,ship] [--ref none]"""
import json
import re
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "bench" / "policy"))
import release_table as rt  # noqa: E402

RUNS = Path.home() / ".cache" / "devkb" / "ext" / "runs"


def load(arms: list[str]) -> list[dict]:
    rows = []
    for f in sorted(RUNS.glob("*/score.json")):
        r = json.loads(f.read_text())
        if r["arm"] not in arms or not r.get("turns"):
            continue
        packs = devkb_calls = 0
        for line in open(f.parent / "stream.jsonl"):
            if '"tool_use"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            for b in (e.get("message") or {}).get("content", []) if e.get("type") == "assistant" else []:
                if b.get("type") == "tool_use" and b["name"] == "Bash":
                    c = (b["input"].get("command") or "")
                    devkb_calls += len(re.findall(r"(?:^|[\s;&|(])devkb\s+(?:symbol|outline|uses|pack|docs)\b", c))
                    packs += len(re.findall(r"(?:^|[\s;&|(])devkb\s+pack\b", c))
        r["_packs"], r["_devkb"] = packs, devkb_calls
        rows.append(r)
    return rows


KEYS = [("pass", lambda r: 1.0 if r["pass"] else 0.0), ("turns", lambda r: float(r["turns"])), ("cost $", lambda r: r["cost"]),
        ("context k tokens", lambda r: r["ctx_tokens"] / 1e3), ("output k tokens", lambda r: r.get("out_tokens", 0) / 1e3),
        ("wall minutes", lambda r: r["seconds"] / 60), ("search calls", lambda r: (r.get("calls") or {}).get("search", 0)),
        ("read-type calls", lambda r: (r.get("calls") or {}).get("read", 0)), ("devkb navigation calls", lambda r: float(r["_devkb"])),
        ("pack calls", lambda r: float(r["_packs"])), ("ran devkb at least once", lambda r: 1.0 if r["_devkb"] else 0.0)]


def main() -> None:
    a = sys.argv[1:]
    arms = a[a.index("--arms") + 1].split(",") if "--arms" in a else ["none", "orig", "ship"]
    rows = load(arms)
    tickets = sorted({r["ticket"] for r in rows})
    by = {(t, m): [r for r in rows if r["ticket"] == t and r["arm"] == m] for t in tickets for m in arms}
    print(f"{len(rows)} runs; per cell " + ", ".join(f"{m} {st.mean(len(by[(t, m)]) for t in tickets):.1f}" for m in arms) + f"; tickets {', '.join(tickets)}\n")
    print("**Per ticket** (pass / turns / cost $ / devkb navigation calls):\n")
    print("| ticket | " + " | ".join(arms) + " |\n|---|" + "---|" * len(arms))
    for t in tickets:
        cells = []
        for m in arms:
            v = by[(t, m)]
            cells.append(f"{sum(r['pass'] for r in v)}/{len(v)} / {st.mean(r['turns'] for r in v):.1f} / {st.mean(r['cost'] for r in v):.2f} / {st.mean(r['_devkb'] for r in v):.1f}" if v else "-")
        print(f"| {t} | " + " | ".join(cells) + " |")
    print("\n**Per arm** (mean over tickets, each ticket weighted equally):\n")
    print("| measure | " + " | ".join(arms) + " |\n|---|" + "---|" * len(arms))
    for k, f in KEYS:
        print(f"| {k} | " + " | ".join(f"{st.mean(st.mean(f(r) for r in by[(t, m)]) for t in tickets if by[(t, m)]):.2f}" for m in arms) + " |")
    print("\n**Paired differences** (first minus second; 90% interval from resampling runs within each ticket):\n")
    pairs = [("ship", "orig"), ("ship", "none"), ("orig", "none")]
    print("| measure | " + " | ".join(f"{x} - {y}" for x, y in pairs if x in arms and y in arms) + " |\n|---|" + "---|" * len([1 for x, y in pairs if x in arms and y in arms]))
    for k, f in KEYS:
        out = []
        for x, y in pairs:
            if x in arms and y in arms:
                cells = [([f(r) for r in by[(t, x)]], [f(r) for r in by[(t, y)]]) for t in tickets if by[(t, x)] and by[(t, y)]]
                m, lo, hi = rt.strat_boot(cells)
                out.append(f"{m:+.2f} ({lo:+.2f} to {hi:+.2f})")
        print(f"| {k} | " + " | ".join(out) + " |")
    fails = [(r["run"], r["failed"][:2]) for r in rows if not r["pass"]]
    print(f"\nFailed hidden checks: {len(fails)} of {len(rows)}" + (": " + "; ".join(f"{n} {f}" for n, f in fails[:12]) if fails else ""))


if __name__ == "__main__":
    main()
