"""Before/after through SPEC-DKB-007 S1..S5: every tri-mode run of the 0.2.13 chain, recounted from its transcript.

For each batch, main's devkb is at some point of the story chain (which story merges are its ancestors); the release
arm is always v0.2.12 and the nonekeep arm has no devkb. Comparing main with release inside one batch (same tickets,
same load) isolates what main's devkb changed. Usage: [DEVKB_BENCH_HARNESS=dir:dir] stories.py OUT.md   (the harness folders holding runs/ and results-*.jsonl)
"""
import collections, glob, json, os, re, statistics as st, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]            # the devkb checkout this file is in
STORIES = [("S1", "bd6091314b5c"), ("S2", "1f14dd5c0571"), ("S3", "6eb10ec995c7"), ("S4", "70e708934e05"), ("S5", "51a415f639b7")]
HARNESS = [Path(p) for p in os.environ.get("DEVKB_BENCH_HARNESS", str(REPO / "bench" / "policy")).split(":")]   # where the runs are
GREP = re.compile(r"(^|[;&|(\n]\s*|\bcd \S+ && |\bxargs\s+)(grep|egrep|rg|git grep)\s")
DEVKB = re.compile(r"(\bdevkb\s+(symbol|uses|outline|pack|tests|callers|query|review|flows|config|search)\b|devkb\.cli\s+(symbol|uses|outline|pack|tests))")


def level(commit):
    if not commit:
        return "none"
    got = "pre-S1"
    for name, c in STORIES:
        if subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", c, commit], capture_output=True).returncode == 0:
            got = name
    return got


sys.path.insert(0, str(REPO / "bench" / "policy"))
import storybench as _sb  # the corrected counting (#258)


def transcript(path):
    t = _sb.transcript(Path(path))
    calls = collections.Counter(grep=t["calls"].get("search", 0), devkb=t["devkb_nav"], selftest=t["devkb_selftest"],
                                read=t["calls"].get("read", 0))
    return t["model_calls"], t["ctx_tokens"], t["out_tokens"], calls


def _old_transcript(path):
    seen, calls, ctx, out = set(), collections.Counter(), 0, 0
    for line in open(path, errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message")
        if e.get("type") != "assistant" or not isinstance(m, dict):
            continue
        u = m.get("usage") or {}
        if m.get("id") not in seen:
            seen.add(m.get("id"))
            ctx += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            out += u.get("output_tokens", 0)
        for x in m.get("content") or []:
            if not isinstance(x, dict) or x.get("type") != "tool_use":
                continue
            n, inp = x["name"], x.get("input") or {}
            if n == "Grep":
                calls["grep"] += 1
            elif n == "Bash":
                c = inp.get("command", "")
                calls["devkb" if DEVKB.search(c) else "grep" if GREP.search(c) else "bash"] += 1
            elif n.startswith("mcp__") and "devkb" in n:
                calls["devkb"] += 1
            elif n in ("Read", "Edit", "Write", "Glob"):
                calls[n.lower()] += 1
            else:
                calls["other"] += 1
    return len(seen), ctx, out, calls


def hooklog():
    by = collections.defaultdict(list)
    for line in open(Path.home() / ".claude/hooks/devkb-guardrail.log", errors="replace"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("session") and r.get("action") != "remind":
            by[r["session"]].append(r)
    return by


def main():
    hooks = hooklog()
    runs = {}
    srcs = [(h, f) for h in HARNESS for f in glob.glob(str(h / "results-*.jsonl"))]
    srcs += [(None, f) for f in glob.glob(str(Path(__file__).resolve().parent / "results" / "results-*.jsonl"))]
    for h, f in srcs:
        if True:
            if not re.search(r"results-\d+\.jsonl$", f):
                continue
            for line in open(f):
                r = json.loads(line)
                if r.get("arm") not in ("nonekeep", "release", "main", "teach", "outline"):
                    continue
                stream = next((x / "runs" / r["run"] / "stream.jsonl" for x in ([h] if h else HARNESS)
                               if (x / "runs" / r["run"] / "stream.jsonl").exists()), None)
                if stream and r["run"] not in runs:
                    runs[r["run"]] = (r, stream)
    rows, levels = [], {}
    for name, (r, stream) in runs.items():
        calls_n, ctx, out, calls = transcript(stream)
        hk = hooks.get(r.get("session"), [])
        if r["arm"] == "main":
            levels.setdefault(r["issue"], level(r.get("devkb_commit")))
        rows.append(dict(issue=r["issue"], arm=r["arm"], ok=bool(r["acceptance"].get("pass") and r["suite_pass"]),
                         cost=r.get("cost", 0), sec=r["seconds"], model_calls=calls_n, ctx=ctx, out=out,
                         grep=calls["grep"], devkb=calls["devkb"], read=calls["read"], edit=calls["edit"] + calls["write"],
                         bash=calls["selftest"], answered=sum(1 for x in hk if x.get("action") in ("alongside", "substitute", "read-answer")),
                         passed=sum(1 for x in hk if x.get("action") == "pass-through"), ans_chars=sum(x.get("chars") or 0 for x in hk),
                         intents=collections.Counter(x.get("intent") for x in hk if x.get("intent"))))
    for r in rows:
        r["level"] = levels.get(r["issue"], "?")
    order = ["pre-S1", "S1", "S2", "S3", "S4", "S5"]
    L = []
    w = L.append
    w("# Before/after through SPEC-DKB-007 S1–S5 (0.2.13 chain, tri-mode runs)\n")
    w(f"{len(rows)} runs recounted from their transcripts. Level = the newest story merged into main's devkb in that batch.\n")
    w("## Per level: averages per run, main arm against release (v0.2.12) in the same batches\n")
    w("| Level | Tickets | Arm | Runs | Pass | Cost $ | Min | Model calls | Context k tok | Output k tok | grep | devkb nav | devkb self-tests | Read | Hook answers | Hook pass-through | Answer chars |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    m = lambda xs, k: st.mean(x[k] for x in xs) if xs else 0
    for lv in order:
        tix = sorted({r["issue"] for r in rows if r["level"] == lv}, key=int)
        if not tix:
            continue
        for arm in ("nonekeep", "release", "main", "teach", "outline"):
            xs = [r for r in rows if r["level"] == lv and r["arm"] == arm]
            if not xs:
                continue
            w(f"| {lv} | {', '.join('#' + t for t in tix)} | {arm} | {len(xs)} | {sum(x['ok'] for x in xs)}/{len(xs)} | {m(xs,'cost'):.2f} | "
              f"{m(xs,'sec')/60:.1f} | {m(xs,'model_calls'):.1f} | {m(xs,'ctx')/1000:.0f} | {m(xs,'out')/1000:.1f} | {m(xs,'grep'):.1f} | "
              f"{m(xs,'devkb'):.2f} | {m(xs,'bash'):.1f} | {m(xs,'read'):.1f} | {m(xs,'answered'):.1f} | {m(xs,'passed'):.1f} | {m(xs,'ans_chars'):.0f} |")
    w("\n## Main against release, paired by ticket (ratio of per-ticket means; 1.00 = same)\n")
    w("| Level | Tickets | Cost | Context | Model calls | grep calls | Pass main | Pass release |")
    w("|---|---|---|---|---|---|---|---|")
    for lv in order:
        tix = sorted({r["issue"] for r in rows if r["level"] == lv}, key=int)
        rat = collections.defaultdict(list)
        pm = pr = n = 0
        for t in tix:
            a = [r for r in rows if r["issue"] == t and r["arm"] == "main"]
            b = [r for r in rows if r["issue"] == t and r["arm"] == "release"]
            if not a or not b:
                continue
            n += 1
            pm += sum(x["ok"] for x in a); pr += sum(x["ok"] for x in b)
            for k in ("cost", "ctx", "model_calls", "grep"):
                if m(b, k):
                    rat[k].append(m(a, k) / m(b, k))
        if n:
            g = lambda k: f"{st.geometric_mean(rat[k]):.2f}" if rat[k] and all(v > 0 for v in rat[k]) else "–"
            w(f"| {lv} | {n} | {g('cost')} | {g('ctx')} | {g('model_calls')} | {g('grep')} | {pm} | {pr} |")
    w("\n## Hook intents seen by the main arm, per level (share of logged decisions)\n")
    for lv in order:
        c = collections.Counter()
        for r in rows:
            if r["level"] == lv and r["arm"] == "main":
                c.update(r["intents"])
        if c:
            tot = sum(c.values())
            w(f"- **{lv}** ({tot} decisions): " + ", ".join(f"{k} {v*100/tot:.0f}%" for k, v in c.most_common(8)))
    Path(sys.argv[1]).write_text("\n".join(L) + "\n")
    print("\n".join(L))


main()
