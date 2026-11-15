"""The README's results chart, from a pooled report: median cost per task by arm, with quality beside each bar.

  python3 bench/readme_chart.py bench/results/2026-11-15-registry/report-all.json docs/img

Writes benchmark-light.svg and benchmark-dark.svg (the README picks one by the reader's colour scheme). One measure
on the axis (cost); quality is printed, never drawn on a second scale.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ARMS = [("plain", "Plain search", "search and read files"),
        ("core", "devkb, 24 tools", "full MCP tool set"),
        ("lean", "devkb, 7 tools", "lean MCP tool set"),
        ("pack", "devkb pack", "pre-computed context")]
THEMES = {
    "light": {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9",
              "base": "#c3c2b7", "bar": "#2a78d6", "ref": "#a9a8a2", "good": "#006300"},
    "dark": {"surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a",
             "base": "#383835", "bar": "#3987e5", "ref": "#6b6a65", "good": "#0ca30c"},
}


def svg(report: dict, t: dict) -> str:
    d, pooled = report["describe"], report["pooled"]
    w, left, bar_w, row, top = 780, 206, 300, 46, 78
    vmax = max(d[a]["median_cost"] for a, *_ in ARMS)
    h = top + row * len(ARMS) + 66
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif" role="img" '
           f'aria-label="Median cost per task by arm, with answer quality">',
           f'<rect width="{w}" height="{h}" rx="8" fill="{t["surface"]}"/>',
           f'<text x="24" y="34" font-size="17" font-weight="600" fill="{t["ink"]}">Cost per task, and how good the answers were</text>',
           f'<text x="24" y="56" font-size="13" fill="{t["ink2"]}">{report["runs"]:,} agent runs, {report["tasks"]} tasks, 7 open-source '
           f'repositories, the same model (Sonnet) in every arm</text>',
           f'<text x="{left + bar_w + 112}" y="{top - 6}" font-size="12" fill="{t["muted"]}">answer quality (0–1)</text>']
    for i, (arm, name, sub) in enumerate(ARMS):
        y = top + i * row
        cost = d[arm]["median_cost"]
        length = max(4.0, bar_w * cost / vmax)
        fill = t["ref"] if arm == "plain" else t["bar"]
        out += [f'<text x="24" y="{y + 17}" font-size="14" font-weight="600" fill="{t["ink"]}">{name}</text>',
                f'<text x="24" y="{y + 34}" font-size="12" fill="{t["ink2"]}">{sub}</text>',
                # 4px rounded data end, square at the baseline
                f'<path d="M{left},{y + 8} h{length - 4:.1f} a4,4 0 0 1 4,4 v12 a4,4 0 0 1 -4,4 h-{length - 4:.1f} z" fill="{fill}">'
                f'<title>{name}: ${cost:.3f} median per task</title></path>']
        label = f"${cost:.3f}"
        if arm != "plain":
            label += f"  ·  {pooled[arm]['cost']['saved']:.0%} cheaper"
        out.append(f'<text x="{left + length + 8:.1f}" y="{y + 25}" font-size="13" fill="{t["ink"]}">{label}</text>')
        q = d[arm]["mean_score"]
        qtext = f"{q:.3f}"
        out.append(f'<text x="{left + bar_w + 112}" y="{y + 25}" font-size="14" font-weight="600" fill="{t["ink"]}">{qtext}</text>')
        if arm != "plain":
            out.append(f'<text x="{left + bar_w + 160}" y="{y + 25}" font-size="12" fill="{t["good"]}">'
                       f'+{pooled[arm]["quality"]["diff"]:.3f}</text>')
    yb = top + row * len(ARMS) + 2
    out += [f'<line x1="{left}" y1="{top}" x2="{left}" y2="{yb - 6}" stroke="{t["base"]}" stroke-width="1"/>',
            f'<text x="24" y="{yb + 20}" font-size="12" fill="{t["muted"]}">Bars: median cost per task (US$). "Cheaper": the '
            f'per-task saving against plain search, averaged over tasks; quality: mean score.</text>',
            f'<text x="24" y="{yb + 38}" font-size="12" fill="{t["muted"]}">95% intervals, per-task detail and '
            f'corrections: bench/results/2026-11-15-registry</text>',
            "</svg>"]
    return "\n".join(out)


def main() -> int:
    report = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (out / f"benchmark-{name}.svg").write_text(svg(report, theme) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
