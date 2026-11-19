"""Recount the transcript fields of saved results from their saved transcripts (#258): turns, model calls, output and
context tokens, devkb navigation and self-tests. Nothing is rerun; the hidden checks and suites are untouched.

Usage: remeasure.py [--runs DIR ...] RESULTS.jsonl [...]   (a row's transcript is <dir>/runs/<run>/stream.jsonl, for the
results file's own folder and each --runs DIR, the harness folders that ran them)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storybench as sb  # noqa: E402

FIELDS = ("turns", "model_calls", "out_tokens", "ctx_tokens", "devkb_queries", "devkb_nav", "devkb_selftest")

args, dirs = sys.argv[1:], []
while "--runs" in args:
    i = args.index("--runs")
    dirs.append(Path(args[i + 1]))
    del args[i:i + 2]
for f in map(Path, args):
    rows, fixed = [json.loads(l) for l in f.read_text().splitlines() if l.strip()], 0
    for r in rows:
        stream = next((d / "runs" / r["run"] / "stream.jsonl" for d in (f.parent, *dirs, sb.B)
                       if (d / "runs" / r["run"] / "stream.jsonl").exists()), None)
        if stream:
            t = sb.transcript(stream)
            r.update({k: t[k] for k in FIELDS})
            fixed += 1
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{f.name}: {fixed} of {len(rows)} rows recounted")
