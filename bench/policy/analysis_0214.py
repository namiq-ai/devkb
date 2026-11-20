"""The facts behind the 0.2.14 benchmark of tickets #301-#307 and #331, as tables (docs/analysis/benchmark-0.2.14-facts.md).

  python bench/policy/analysis_0214.py [--results DIR] [--runs DIR] [--guard-log FILE]
  (--results bench/policy/rerun-0.2.14 for the 16-run re-run on the final harness; the default is the 48-run baseline)

Reads results-<N>.jsonl (committed, one row per run) and, from --runs (default bench/policy/runs: the run streams, not
committed: they hold local paths), each run's stream.jsonl. Every number in the document comes from here. Standard library only.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

B = Path(__file__).resolve().parent
TICKETS = ("301", "302", "303", "304", "305", "306", "307", "331")
ARMS = ("none", "main")
DENIED = re.compile(r"requires approval|can't be checked|obfuscation|contains multiple operations")
MISSING_DATA = re.compile(r"audit-0\.2\.13|audit/repro|\baudit\b")
BG = "did not complete within its 120s timeout"


def arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


RES = Path(arg("--results", str(B)))                  # the directory of the results-<N>.jsonl rows (the 48-run baseline is bench/policy itself)
RUNS = Path(arg("--runs", str(B / "runs")))
GUARD = Path(arg("--guard-log", str(Path.home() / ".claude" / "hooks" / "devkb-guardrail.log")))


def ts(e):
    t = e.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() if t else None


def rows():
    out = []
    for t in TICKETS:
        for line in open(RES / f"results-{t}.jsonl"):
            if line.strip():
                out.append(json.loads(line))
    return out


def stream(run):
    return [json.loads(l) for l in open(RUNS / run / "stream.jsonl") if l.strip()]


def uses_and_results(ev):
    """(tool_use id -> (name, input, ts), tool_result id -> (text, is_error, ts)) of one stream."""
    uses, res = {}, {}
    for e in ev:
        m = e.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        for x in m["content"]:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_use":
                uses[x["id"]] = (x["name"], x["input"] if isinstance(x["input"], dict) else {}, ts(e))
            elif x.get("type") == "tool_result":
                c = x.get("content")
                res[x["tool_use_id"]] = (c if isinstance(c, str) else json.dumps(c), bool(x.get("is_error")), ts(e))
    return uses, res


def classify(name, inp, denied):
    cmd = inp.get("command", "") if name == "Bash" else ""
    if denied:
        return "retry after a denied command"
    if name in ("Edit", "Write", "MultiEdit"):
        return "edit/write"
    if name == "Monitor" or (name == "Bash" and re.search(r"\buntil\b|\bsleep\b", cmd)) or (name == "Read" and "/tasks/" in inp.get("file_path", "")):
        return "waiting on a background run"
    if name == "Bash" and "pytest" in cmd:
        return "running tests"
    if name == "Bash" and re.search(r"\bgit\b", cmd):
        return "git"
    if name in ("Read", "Grep", "Glob") or (name == "Bash" and re.search(r"\b(sed|cat|head|tail|grep|ls|wc|find|nl|awk)\b", cmd)):
        return "reading/searching code"
    return "other"


def table(head, body):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, r)) + " |" for r in body]


def main():
    R = rows()
    by = lambda arm, t=None: [r for r in R if r["arm"] == arm and (t is None or r["issue"] == t)]
    mean = lambda xs: st.mean(xs) if xs else float("nan")
    print("## 1. Outcome per ticket and arm (3 runs each)\n")
    body = []
    for t in TICKETS:
        for a in ARMS:
            x = by(a, t)
            body.append((f"#{t}", a, len(x), f"{sum(bool(r['acceptance'].get('pass')) for r in x)}/{len(x)}", f"{sum(r['suite_pass'] for r in x)}/{len(x)}",
                         f"{mean([r['turns'] for r in x]):.1f}", f"{mean([r['ctx_tokens'] for r in x]) / 1e3:.0f}", f"{mean([r['cost'] for r in x]):.2f}",
                         f"{mean([r['seconds'] for r in x]) / 60:.1f}", "; ".join(sorted({r['diff'] for r in x}))[:60]))
    print("\n".join(table(("Ticket", "Arm", "Runs", "Hidden check", "Suite", "Turns", "Context k", "Cost $", "Wall min", "Solution size (distinct)"), body)))
    print("\n### Totals over the 8 tickets (24 runs per arm)\n")
    body = []
    for a in ARMS:
        x = by(a)
        body.append((a, len(x), f"{sum(bool(r['acceptance'].get('pass')) for r in x)}/{len(x)}", f"{sum(r['suite_pass'] for r in x)}/{len(x)}",
                     f"{mean([r['turns'] for r in x]):.1f}", f"{mean([r['model_calls'] for r in x]):.1f}", f"{mean([r['ctx_tokens'] for r in x]) / 1e3:.0f}",
                     f"{mean([r['out_tokens'] for r in x]) / 1e3:.1f}", f"{mean([r['cost'] for r in x]):.3f}", f"{mean([r['seconds'] for r in x]) / 60:.1f}",
                     f"{st.median([r['seconds'] for r in x]) / 60:.1f}"))
    print("\n".join(table(("Arm", "Runs", "Hidden check", "Suite", "Turns", "Model calls", "Context k", "Output k", "Cost $", "Wall mean min", "Wall median min"), body)))
    print("\nHidden-check failures:", "; ".join(f"{r['run']} ({', '.join(k for k, v in r['acceptance'].items() if v is False and k != 'pass')})" for r in R if not r["acceptance"].get("pass")) or "none")

    print("\n## 2. devkb use by the agents\n")
    c = collections.Counter()
    first = collections.Counter()
    for r in R:
        ev = stream(r["run"])
        uses, res = uses_and_results(ev)
        arm = r["arm"]
        for i, (name, inp, _) in enumerate(uses.values()):
            if name == "Bash":
                c[(arm, "bash")] += 1
                if re.search(r"(^|[\s;&|(])(\S*/)?devkb\s+(symbol|uses|outline|pack|docs|misses|tests|config|flows|review|build|init|query)\b|-m\s+devkb", inp.get("command", "")):
                    c[(arm, "bash invoking devkb")] += 1
            if name.startswith("mcp__devkb"):
                c[(arm, "mcp devkb")] += 1
        c[(arm, "runs")] += 1
        c[(arm, "devkb_nav (row)")] += r["devkb_nav"]
        c[(arm, "devkb_queries (row)")] += r["devkb_queries"]
        if arm == "main" and uses:
            n, inp, _ = next(iter(uses.values()))
            first[n] += 1
    print("\n".join(table(("Arm", "Runs", "Bash commands", "Bash invoking devkb", "MCP devkb calls", "Sum of devkb_nav", "Sum of devkb_queries"),
                          [(a, c[(a, "runs")], c[(a, "bash")], c[(a, "bash invoking devkb")], c[(a, "mcp devkb")], c[(a, "devkb_nav (row)")], c[(a, "devkb_queries (row)")]) for a in ARMS])))
    print("\nFirst tool of each devkb-arm run:", dict(first))

    print("\n## 3. Where the extra turns went (tool calls per run)\n")
    cat = {a: collections.Counter() for a in ARMS}
    n = collections.Counter()
    bg = collections.Counter()
    dur = {a: [] for a in ARMS}
    own_to = collections.Counter()
    pytest_calls = 0
    denied_n = collections.Counter()
    missing = collections.Counter()
    saidcant = collections.Counter()
    sysden = collections.Counter()
    n7 = collections.Counter(r['arm'] for r in R if r['issue'] != '331')
    for r in R:
        ev = stream(r["run"])
        uses, res = uses_and_results(ev)
        a = r["arm"]
        n[a] += 1
        hit = False
        for tid, (name, inp, t0) in uses.items():
            text, err, t1 = res.get(tid, ("", False, None))
            den = err and bool(DENIED.search(text))
            denied_n[a] += den
            cat[a][classify(name, inp, den)] += 1
            cmd = inp.get("command", "") if name == "Bash" else ""
            if BG in text:
                hit = True
                bg[(a, "commands moved to the background by the 120 s default")] += 1
            if name == "Bash" and "pytest" in cmd:
                pytest_calls += 1
                own_to[(a, "pytest calls")] += 1
                own_to[(a, "pytest calls with own timeout")] += bool(inp.get("timeout"))
                if not re.search(r"pytest[^|;&]*(tests/|::| -k )", cmd) and not den and t0 and t1 and t1 - t0 > 5:
                    dur[a].append(t1 - t0)
            if name == "Bash" and MISSING_DATA.search(cmd) and r["issue"] != "331":
                missing[a] += 1
        bg[(a, "runs with a command backgrounded by the 120 s default")] += hit
        sysden[a] += sum(1 for e in ev if e.get("type") == "system" and e.get("subtype") == "permission_denied")
        for e in ev:
            m = e.get("message")
            if e.get("type") == "assistant" and isinstance(m, dict) and r["issue"] != "331":
                for x in m.get("content") or []:
                    if isinstance(x, dict) and x.get("type") == "text" and re.search(r"(could not|couldn't|did not|didn't|can't|cannot|not) (run|reproduce)|isn't in this|is not in this|not in this (checkout|clone)|blocked every attempt", x["text"], re.I):
                        saidcant[a] += 1
                        break
    keys = sorted(set(cat["none"]) | set(cat["main"]))
    body = [(k, f"{cat['none'][k] / n['none']:.1f}", f"{cat['main'][k] / n['main']:.1f}", f"{cat['main'][k] / n['main'] - cat['none'][k] / n['none']:+.1f}") for k in keys]
    tn = sum(cat["none"].values()) / n["none"]
    tm = sum(cat["main"].values()) / n["main"]
    body.append(("**total tool calls**", f"{tn:.1f}", f"{tm:.1f}", f"{tm - tn:+.1f}"))
    print("\n".join(table(("Category", "none", "main (devkb)", "Difference"), body)))

    print("\n## 4. The 120-second default and the suite's duration\n")
    print("\n".join(table(("Arm", "Runs with a command backgrounded by the default", "Commands backgrounded", "pytest calls", "pytest calls that set their own timeout", "Full-suite commands that ran (n)", "Median s", "Mean s", "Max s"),
                          [(a, f"{bg[(a, 'runs with a command backgrounded by the 120 s default')]}/{n[a]}", bg[(a, 'commands moved to the background by the 120 s default')],
                            own_to[(a, 'pytest calls')], own_to[(a, 'pytest calls with own timeout')], len(dur[a]),
                            f"{st.median(dur[a]):.0f}" if dur[a] else "-", f"{st.mean(dur[a]):.0f}" if dur[a] else "-", f"{max(dur[a]):.0f}" if dur[a] else "-") for a in ARMS])))

    print("\n## 5. Permission denials and the missing reproduction data\n")
    print("\n".join(table(("Arm", "Permission-denied events in the stream", "per run", "Tool results that are denials", "per run", "Calls aimed at the audit data (#301-#307)", "Final reports saying a reproduction could not be run (#301-#307)"),
                          [(a, sysden[a], f"{sysden[a] / n[a]:.1f}", denied_n[a], f"{denied_n[a] / n[a]:.1f}", f"{missing[a]} ({missing[a] / n7[a]:.1f}/run)", f"{saidcant[a]}/{n7[a]}") for a in ARMS])))

    print("\n## 6. Starting context\n")
    fc = {a: [] for a in ARMS}
    for r in R:
        ms = {}
        for e in stream(r["run"]):
            m = e.get("message")
            if e.get("type") == "assistant" and isinstance(m, dict) and m.get("id") and m["id"] not in ms:
                u = m.get("usage") or {}
                ms[m["id"]] = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if ms:
            fc[r["arm"]].append(next(iter(ms.values())))
    print("\n".join(table(("Arm", "First-call context, mean tokens", "min", "max"), [(a, f"{mean(fc[a]):.0f}", min(fc[a]), max(fc[a])) for a in ARMS])))

    print("\n## 7. The hook (devkb-arm runs; the log keeps names, intents and reasons, not the command text)\n")
    sess = {r["session"]: r["run"] for r in R if r["arm"] == "main"}
    log = []
    if GUARD.exists():
        for line in open(GUARD, errors="replace"):
            try:
                x = json.loads(line)
            except ValueError:
                continue
            if x.get("session") in sess:
                log.append(x)
    print(f"Log rows for the {len(sess)} devkb-arm runs: {len(log)}; runs with no row: {sorted(set(sess.values()) - {x['session'] and sess[x['session']] for x in log})}\n")
    print("By action:", dict(collections.Counter(x.get("action") for x in log)))
    pt = [x for x in log if x.get("action") == "pass-through"]
    print("Pass-through reasons:", dict(collections.Counter(x.get("reason") for x in pt)))
    print("Pass-through verdicts:", dict(collections.Counter(v for x in pt for v in x.get("verdicts") or [])))
    print("Pass-through characters sent to the agent:", sum(x.get("chars") or 0 for x in pt))
    print("Reminder intents:", dict(collections.Counter(x.get("intent") for x in log if x.get("action") == "remind")))
    print("Answers beside grep (alongside):", [(sess[x["session"]], x.get("names"), x.get("answer_chars")) for x in log if x.get("action") == "alongside"])

    print("\n## 8. Per run\n")
    print("\n".join(table(("Run", "Wall min", "Turns", "Model calls", "Context k", "Cost $", "Hidden", "Suite", "Hook actions"),
                          [(r["run"], f"{r['seconds'] / 60:.1f}", r["turns"], r["model_calls"], f"{r['ctx_tokens'] / 1e3:.0f}", f"{r['cost']:.2f}", "pass" if r["acceptance"].get("pass") else "FAIL",
                            "pass" if r["suite_pass"] else "FAIL", json.dumps(r.get("guardrail_actions") or {})) for r in sorted(R, key=lambda r: r["run"])])))


if __name__ == "__main__":
    main()
