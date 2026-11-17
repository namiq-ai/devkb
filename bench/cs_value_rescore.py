"""Rescore committed value-report transcripts: the compiler truth alone, and with the question's hand corrections.

  python bench/cs_value_rescore.py QUESTIONS.json RUNS_DIR [RUNS_DIR ...]

Each RUNS_DIR holds `<arm>-<repo>-<Method>-r<N>.jsonl` transcripts (bench/cs_value.py run). Prints, per directory and
arm, mean precision and recall over runs, then per question.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cs_value as cv  # noqa: E402


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def main() -> int:
    qs = json.loads(Path(sys.argv[1]).read_text())
    print("| runs | arm | precision, compiler truth | recall | precision, corrected | recall | runs |")
    print("|---|---|---|---|---|---|---|")
    per_q = []
    for d in map(Path, sys.argv[2:]):
        for arm in ("plain", "devkb"):
            a, b, n = [], [], 0
            for q in qs:
                qa, qb = [], []
                for p in sorted(d.glob(f"{arm}-{cv.short(q['repo'])}-{q['name']}-r*.jsonl")):
                    text = cv.stream_stats(p)["result"] or ""
                    qa.append(cv.score(q, text, compiler_only=True))
                    qb.append(cv.score(q, text))
                    n += 1
                a += qa
                b += qb
                if qa:
                    per_q.append((d.name, arm, q["target"], mean([s["P"] for s in qa]), mean([s["P"] for s in qb]),
                                  mean([s["R"] for s in qb])))
            if n:
                print(f"| {d.name} | {arm} | {mean([s['P'] for s in a]):.3f} | {mean([s['R'] for s in a]):.2f} | "
                      f"{mean([s['P'] for s in b]):.3f} | {mean([s['R'] for s in b]):.2f} | {n} |")
    print("\n| runs | arm | question | precision, compiler truth | precision, corrected | recall, corrected |")
    print("|---|---|---|---|---|---|")
    for r in per_q:
        print(f"| {r[0]} | {r[1]} | `{r[2]}` | {r[3]:.2f} | {r[4]:.2f} | {r[5]:.2f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
