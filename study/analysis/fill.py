#!/usr/bin/env python3
"""Generate table-confirmatory.tex from results-sonnet.json and results-haiku.json (no hand-typed numbers).

  python3 fill.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent


def pct(x):
    return f"{100 * x:+.0f}".replace("-", "$-$")


def num(x):
    return f"{x:+.3f}".replace("-", "$-$")


def row(model, arm, res, hyp=""):
    c, q = res["pooled"][arm]["cost"], res["pooled"][arm]["quality"]
    d = res["describe"][arm]
    return (f"{model} & {arm} & {pct(c['saved'])}\\% [{pct(c['lo'])}, {pct(c['hi'])}] & "
            f"{num(q['diff'])} [{num(q['lo'])}, {num(q['hi'])}] & {d['median_turns']:g} & {hyp} \\\\")


def main():
    s = json.loads((STUDY / "results" / "results-sonnet.json").read_text())
    h = json.loads((STUDY / "results" / "results-haiku.json").read_text())
    lines = [r"\begin{table}[t]\centering\small",
             r"\caption{Confirmatory study: cost saved against plain (positive is cheaper) and quality difference, "
             rf"95\% bootstrap intervals; {s['tasks']} held-out tasks, {s['runs']} Sonnet and {h['runs']} Haiku runs. "
             rf"Plain: median {s['describe']['plain']['median_turns']:g} turns (Sonnet), mean score "
             rf"{s['describe']['plain']['mean_score']:.2f}.}}\label{{tab:confirmatory}}",
             r"\setlength{\tabcolsep}{3pt}",
             r"\resizebox{\columnwidth}{!}{\begin{tabular}{llrrrl}\toprule",
             r"Model & Arm & Cost saved & Quality diff. & Turns & Hyp. \\ \midrule"]
    hyp = {"core": "H3", "lean": "H2", "pack": "H1"}
    for arm in ("core", "workflow", "lean", "pack"):
        lines.append(row("Sonnet", arm, s, hyp.get(arm, "")))
    lines.append(r"\midrule")
    for arm in ("lean", "pack"):
        lines.append(row("Haiku", arm, h, "H5"))
    lines += [r"\bottomrule\end{tabular}}", r"\end{table}"]
    (STUDY / "paper" / "table-confirmatory.tex").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
