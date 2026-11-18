"""report.py ISSUE [ISSUE ...] : the per-arm table of SPEC-DKB-004 §6 (means by arm), plus outcomes per run."""
import json
import statistics as st
import sys
from pathlib import Path

B = Path(__file__).resolve().parent
NAMES = {"devkb": "devkb", "guardrail": "devkb + guardrail"}


def fmt_tok(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


for issue in sys.argv[1:]:
    rows = [json.loads(l) for l in open(B / f"results-{issue}.jsonl")]
    print(f"\n#{issue}: means by arm\n")
    print("| Arm | Runs | Wall | Turns | Model calls | Grep | File load | devkb | Guardrail fired | Tokens (ctx / out) | Cost | Suite green | Acceptance |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm in ("devkb", "guardrail"):
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        m = lambda f: st.mean(f(r) for r in rs)
        acc = [r["acceptance"]["pass"] for r in rs if r.get("acceptance")]
        print(f"| {NAMES[arm]} | {len(rs)} | {m(lambda r: r['seconds']) / 60:.0f} min | {m(lambda r: r['turns']):.0f} | "
              f"{m(lambda r: r['model_calls']):.0f} | {m(lambda r: r['calls'].get('search', 0)):.1f} | "
              f"{m(lambda r: r['calls'].get('read', 0)):.1f} | {m(lambda r: r['devkb_queries']):.1f} | "
              f"{m(lambda r: r['guardrail_fired']):.1f} | {fmt_tok(m(lambda r: r['ctx_tokens']))} / {fmt_tok(m(lambda r: r['out_tokens']))} | "
              f"${m(lambda r: r['cost']):.2f} | {sum(r['suite_pass'] for r in rs)}/{len(rs)} | "
              f"{(str(sum(acc)) + '/' + str(len(acc))) if acc else 'n/a'} |")
    print("\nPer run:\n")
    for r in rows:
        print(f"- {r['run']}: exit {r['exit']}, {r['seconds'] // 60} min, ${r['cost']:.2f}, devkb {r['devkb_queries']}, "
              f"guardrail {r['guardrail_fired']}, grep {r['calls'].get('search', 0)}, suite {'green' if r['suite_pass'] else 'RED'}, "
              f"{r['diff']}, acceptance {json.dumps(r.get('acceptance'))}")
