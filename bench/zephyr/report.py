#!/usr/bin/env python3
"""Tables from the run records of the Zephyr benchmark (#447): per task and arm, then per arm. Medians with ranges, counts with their n."""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics  # noqa: E402
import zbench  # noqa: E402


def load() -> list[dict]:
    out = []
    for f in sorted(zbench.OUT.glob("z*-r*/record.json")):
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        if "hidden" in r:
            r["metrics"] = metrics.parse(f.parent / "stream.jsonl")      # always from the raw stream: the parser may have improved since the run
            out.append(r)
    return out


def valid(r: dict) -> bool:
    return not r["entry_problems"] and r["exit"] in (0, "0") and not r["metrics"]["is_error"]


def med(xs):
    xs = [x for x in xs if x is not None]
    return "-" if not xs else f"{st.median(xs):.3g} [{min(xs):.3g}-{max(xs):.3g}]"


def row(rs: list[dict]) -> list[str]:
    m = [r["metrics"] for r in rs]
    g = [x for x in m if x["graph_calls"]]
    outcomes: dict[str, int] = defaultdict(int)
    for x in m:
        for k, v in x["graph_outcomes"].items():
            outcomes[k] += v
    return [str(len(rs)), f"{sum(1 for r in rs if r['hidden'].get('passed'))}/{len(rs)}", med([x["cost_usd"] for x in m]), med([x["turns"] for x in m]),
            med([x["tokens_total"] for x in m]), med([x["navigation_calls"] for x in m]), med([x["tool_calls"] for x in m]),
            med([x["result_chars_total"] for x in m]), f"{len(g)}/{len(rs)}", med([x["graph_calls"] for x in g]) if g else "-",
            ", ".join(f"{k}:{v}" for k, v in sorted(outcomes.items())) or "-", med([x["first_graph_turn"] for x in g]),
            med([r["change"]["ref_recall"] for r in rs]), med([r["seconds"] for r in rs])]


HEAD = ["n", "hidden pass", "cost $", "turns", "tokens", "nav calls", "tool calls", "result chars", "runs using graph", "graph calls", "graph outcomes",
        "first graph turn", "ref-file recall", "seconds"]


def table(title: str, groups: dict) -> str:
    lines = [f"### {title}", "", "| " + " | ".join(["group"] + HEAD) + " |", "|" + "---|" * (len(HEAD) + 1)]
    for k in sorted(groups):
        lines.append("| " + " | ".join([str(k)] + row(groups[k])) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    rs = load()
    ok = [r for r in rs if valid(r)]
    print(f"{len(rs)} records, {len(ok)} valid, {len(rs) - len(ok)} excluded (entry problem, non-zero exit or error result)\n")
    by_arm, by_task_arm = defaultdict(list), defaultdict(list)
    for r in ok:
        by_arm[r["arm"]].append(r)
        by_task_arm[(r["task"], r["arm"])].append(r)
    print(table("By arm (all tasks)", by_arm))
    print(table("By task and arm", {f"{t} {a}": v for (t, a), v in by_task_arm.items()}))
    bad = [r for r in rs if not valid(r)]
    if bad:
        print("Excluded: " + ", ".join(f"{r['tag']} ({'; '.join(r['entry_problems']) or r['exit']})" for r in bad))


if __name__ == "__main__":
    main()
