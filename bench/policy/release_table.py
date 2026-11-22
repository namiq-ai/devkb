"""The release table of the dual/tri-mode benchmark (#222, #223).

  python release_table.py TICKET=RESULTS.jsonl [TICKET=RESULTS.jsonl ...] [--allow-mixed-checks]

One row per ticket and arm: the mean and the spread (min–max) of wall time, context and cost, devkb's share of the
searches, the hidden check and the suite. A difference from the no-devkb arm is marked `within noise` when the two arms'
ranges overlap. The release totals carry a bootstrap 90% interval for the difference in cost and context per run,
resampled over tickets.

A ticket whose runs were scored by different versions of its hidden check (`accept_sha256`) is refused, named, unless
--allow-mixed-checks is given; re-score with `policybench.py score TICKET` so every run carries the same check.
"""
from __future__ import annotations

import json
import random
import re
import statistics as st
import sys
from pathlib import Path

B = Path(__file__).resolve().parent
sys.path.insert(0, str(B))
import storybench as sb  # noqa: E402  (the one rule for devkb commands, #258)
NONE = ("none", "nonekeep", "nonehid")        # the no-devkb arms; rmain and router are compared with them
ORDER = ("nonekeep", "none", "release", "climain", "cli130", "userpolicy", "userinit", "short", "inject", "main", "rmain", "router", "ctx", "nonehid", "mainhid", "rmainhid", "routerhid", "ctxhid")
HIDDEN_LOCATION = ("nonehid", "mainhid", "rmainhid", "routerhid", "ctxhid")          # the ticket's location withheld (#337); compared with each other


def location_given(arm: str) -> bool:
    return arm not in HIDDEN_LOCATION


def base_for(arm: str, arms: list[str], sums: dict) -> dict | None:
    """The no-devkb arm an arm is compared with: the one given the ticket the same way, hidden against hidden (#337)."""
    return next((sums[b] for b in arms if b in NONE and location_given(b) == location_given(arm)), None)


def counts(run: str) -> tuple[int, int, int] | None:
    """(devkb queries the agent made, devkb runs on its own code, searches the hook replaced) in one transcript, or None
    when the transcript is not under bench/policy/runs (#304): the row's stored counts are used then, never zeros."""
    nav = own = subst = 0
    edited, root = False, None
    path = B / "runs" / run / "stream.jsonl"
    if not path.exists():
        return None
    for line in open(path):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            root = e.get("cwd") or root
        m = e.get("message")
        if not isinstance(m, dict):
            continue
        for x in m.get("content") or []:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_use":
                if x["name"].startswith("mcp__devkb"):
                    nav += 1
                    continue
                n, o = sb.devkb_commands(x.get("input", {}).get("command", "") or "", edited)
                nav, own = nav + n, own + o
                fp = str(x.get("input", {}).get("file_path", ""))
                if x["name"] in ("Edit", "Write", "MultiEdit", "NotebookEdit") and sb.edits_devkb_code(fp, root):
                    edited = True
            elif x.get("type") == "tool_result":
                c = x.get("content")
                c = c if isinstance(c, str) else json.dumps(c)
                if "devkb answered this search from the graph" in c[:300]:
                    subst += 1
    return nav, own, subst


GUARD_LOG = Path.home() / ".claude" / "hooks" / "devkb-guardrail.log"
_LOG: list[dict] | None = None


def guard_rows(session: str) -> list[dict]:
    """The guardrail's decision lines for one run's session (#218): what the hook did and what the agent was given."""
    global _LOG
    if _LOG is None:
        _LOG = []
        if GUARD_LOG.exists():
            for line in open(GUARD_LOG, errors="replace"):
                try:
                    _LOG.append(json.loads(line))
                except ValueError:
                    pass
    return [r for r in _LOG if session and r.get("session") == session and r.get("action") not in (None, "remind", "pass-through")]


def contaminated(r: dict) -> list[str]:
    """What an agent or the harness wrote in the harness repository during the run, apart from moving a run to
    `runs-archive/`: the benchmark's own housekeeping, which no agent can reach (#340). Rows scored before the harness learned
    that carry such paths."""
    return [x for x in r.get("contaminated") or [] if "runs-archive/" not in x]


# The repetition rule (#368, docs/BENCHMARK.md "How many runs a claim needs"). PROPOSED values, the bench owner's to confirm: they set what every ticket costs.
MIN_RUNS_PER_ARM = 7          # a per-ticket claim about cost or context needs this many runs in each arm
LARGE_EFFECT = 0.40           # the two-arm step of a ticket (3 runs) may name a direction only when the cost or context effect is larger than this
MIN_POOLED_TICKETS = 6        # a release claim pools at least this many tickets, at 3 runs per arm


def per_run(r: dict) -> dict:
    c = counts(r["run"])
    nav, own, sub = c if c else (r.get("devkb_nav", 0), r.get("devkb_selftest", 0), 0)
    a = r.get("acceptance") or {}
    g = guard_rows(r.get("session", ""))
    rf = r.get("refetch")                         # devkb queries followed by a grep or read of the same target; absent in old rows
    return {"rq": rf["queries"] if rf else None, "rf": rf["refetched"] if rf else None, "turns": r["turns"], "grep": r["calls"].get("search", 0), "nav": nav, "own": own, "sub": sub, "ctx": r["ctx_tokens"],
            "out": r.get("out_tokens", 0),
            "cost": r["cost"], "cut_off": bool(r.get("cut_off")), "wall": r["seconds"] / 60, "ok": bool(a.get("pass")), "suite": bool(r["suite_pass"]),
            "flaky": bool(r.get("suite_flaky")),
            "answers": len(g), "answer_chars": sum(x.get("answer_chars") or x.get("chars") or 0 for x in g)}


def summary(xs: list[dict]) -> dict:
    out = {"n": len(xs), "ok": sum(x["ok"] for x in xs), "suite": sum(x["suite"] for x in xs),
           "flaky": sum(x.get("flaky", False) for x in xs), "cut_off": sum(x.get("cut_off", False) for x in xs)}
    for k in ("turns", "grep", "nav", "own", "sub", "ctx", "out", "cost", "wall", "answers", "answer_chars", "rq", "rf"):
        vals = [x.get(k) for x in xs if x.get(k) is not None] or [0]     # a cut-off run's cost is unknown: not a zero (#303)
        out[k] = st.mean(vals)
        out[k + "_lo"], out[k + "_hi"] = min(vals), max(vals)
        out[k + "_cv"] = st.stdev(vals) / out[k] if len(vals) >= 2 and out[k] else None       # the run-to-run spread the rule rests on (#368)
    return out


def direction_note(m: dict, base: dict, dc: float, dk: float) -> str:
    """What a per-ticket difference may claim at this many runs (#368). Both arms at MIN_RUNS_PER_ARM or more: it may be read. Fewer: only an effect
    larger than LARGE_EFFECT names a direction; a smaller one is marked `below n`, because at 3 runs the sign flips from ticket to ticket."""
    if min(m["n"], base["n"]) >= MIN_RUNS_PER_ARM:
        return ""
    if max(abs(dc), abs(dk)) / 100 > LARGE_EFFECT:
        return f" (large effect, {min(m['n'], base['n'])} runs per arm)"
    return f" (below n: {MIN_RUNS_PER_ARM} runs per arm to read an effect under {LARGE_EFFECT:.0%}; this has {min(m['n'], base['n'])})"


def within_noise(a: dict, b: dict, k: str) -> bool:
    """The two arms' ranges overlap: the difference is not larger than the runs' own spread."""
    return not (a[k + "_hi"] < b[k + "_lo"] or b[k + "_hi"] < a[k + "_lo"])


def bootstrap(diffs: list[float], n: int = 2000, seed: int = 222) -> tuple[float, float]:
    """90% interval of the mean of per-ticket differences, resampled over tickets."""
    if not diffs:
        return 0.0, 0.0
    rnd = random.Random(seed)
    means = sorted(st.mean(rnd.choice(diffs) for _ in diffs) for _ in range(n))
    return means[int(0.05 * n)], means[int(0.95 * n) - 1]


def check_hashes(ticket: str, rows: list[dict]) -> str | None:
    """None when every run of the ticket was scored by one version of its hidden check."""
    seen = {r.get("accept_sha256") for r in rows}
    if len(seen) > 1:
        return f"#{ticket}: runs scored by {len(seen)} versions of the hidden check ({', '.join(sorted(str(h)[:8] for h in seen))})"
    return None


def refetched(xs: list[dict]) -> str:
    """Per run: devkb queries that were followed by a grep or read of the same target / all devkb queries with a target.
    "n/a" for an arm whose rows predate the measure (run `remeasure.py` to fill them)."""
    known = [x for x in xs if x.get("rq") is not None]
    if not known:
        return "n/a"
    return f"{st.mean(x['rf'] for x in known):.1f}/{st.mean(x['rq'] for x in known):.1f}"


def cv_note(m: dict) -> str:
    """The cell's coefficient of variation of cost, printed beside its range (#368)."""
    return f", CV {m['cost_cv']:.2f}" if m.get("cost_cv") is not None else ""


def fmt_range(m: dict, k: str, scale: float = 1.0, unit: str = "", digits: int = 1) -> str:
    f = f"{{:.{digits}f}}"
    return f"{f.format(m[k] / scale)}{unit} ({f.format(m[k + '_lo'] / scale)}–{f.format(m[k + '_hi'] / scale)})"


def start_section(pairs: list[tuple[str, list[dict]]]) -> list[str]:
    """The start of each run apart from its totals (#331): the first model call's context (policy, hook and tool text, no
    work yet) and the number of tests the arm's checkout collects. A ticket whose arms collect different numbers gets a
    warning: a difference in cost, turns or wall time between them then includes the suite's size."""
    out = ["", "| Ticket | Arm | First-call context k | Tests collected | Commands backgrounded per run | Hook outputs per run |", "|---|---|---|---|---|---|"]
    warn = []
    for t, rows in pairs:
        arms = sorted({r["arm"] for r in rows}, key=lambda a: ORDER.index(a) if a in ORDER else 99)
        seen = {}
        for a in arms:
            fc = [r["first_ctx"] for r in rows if r["arm"] == a and r.get("first_ctx") is not None]
            tc = sorted({r["tests_collected"] for r in rows if r["arm"] == a and r.get("tests_collected") is not None})
            seen[a] = tc
            bg = [r["backgrounded"] for r in rows if r["arm"] == a and r.get("backgrounded") is not None]
            ho = [r["hook_outputs"] for r in rows if r["arm"] == a and r.get("hook_outputs") is not None]    # #330
            out.append(f"| #{t} | {a} | {f'{st.mean(fc) / 1e3:.1f}' if fc else 'unknown'} | {', '.join(map(str, tc)) if tc else 'unknown'} | "
                       f"{f'{st.mean(bg):.1f}' if bg else 'unknown'} | {f'{st.mean(ho):.1f}' if ho else 'unknown'} |")
        known = {a: tc for a, tc in seen.items() if tc}
        if len({tuple(v) for v in known.values()}) > 1:
            warn.append(f"#{t}: the arms collect different numbers of tests ({'; '.join(f'{a} {tc}' for a, tc in known.items())}): "
                        "a difference in cost, turns or wall time between them includes the suite's size (#331)")
    return out + [f"WARNING {w}" for w in warn]


def strat_boot(cells: list[tuple[list[float], list[float]]], n: int = 3000, seed: int = 222) -> tuple[float, float, float]:
    """(mean, low, high) of the mean difference between two arms, 90%: for each ticket, resample the runs of each arm with
    replacement, take the difference of the arm means, then average the tickets, which weigh the same. Runs vary within a ticket
    by more than the tickets' means differ, so resampling the six per-ticket means alone understates the spread, and treating
    all runs as one sample ignores which ticket they belong to."""
    rnd = random.Random(seed)
    def once(resample: bool) -> float:
        return st.mean(st.mean(rnd.choices(a, k=len(a)) if resample else a) - st.mean(rnd.choices(b, k=len(b)) if resample else b)
                       for a, b in cells)
    ds = sorted(once(True) for _ in range(n))
    return once(False), ds[int(.05 * n)], ds[int(.95 * n) - 1]


def compare_arms(pairs: list[tuple[str, list[dict]]], a: str, b: str) -> list[str]:
    """Arm `a` against arm `b` run for run, whichever they are: the table above compares with the no-devkb arm only. Only the
    tickets that have both arms count; the rows are runs of one batch only if the caller has checked that they are."""
    keys = {"turns": lambda x: x["turns"], "cost $": lambda x: x["cost"], "context k": lambda x: x["ctx"] / 1e3,                  # a cut-off run's cost is None: left out (#303)
            "search calls": lambda x: x["grep"], "devkb nav": lambda x: x["nav"], "hidden check passed": lambda x: 1.0 if x["ok"] and x["suite"] else 0.0}
    cells = []
    for t, rows in pairs:
        ra, rb = ([per_run(r) for r in rows if r["arm"] == arm and not contaminated(r)] for arm in (a, b))
        if ra and rb:
            cells.append((t, ra, rb))
    if not cells:
        return [f"No ticket has both {a} and {b}."]
    out = ["", f"{a} against {b}, {len(cells)} tickets ({', '.join('#' + c[0] + f' {len(c[1])}/{len(c[2])}' for c in cells)} runs), "
           "90% interval from resampling runs within each ticket, tickets weighted equally:", "",
           f"| | {b} | {a} | difference (90% interval) |", "|---|---|---|---|"]
    for k, f in keys.items():
        data = [([f(x) for x in ra if f(x) is not None], [f(x) for x in rb if f(x) is not None]) for _t, ra, rb in cells]
        data = [d for d in data if d[0] and d[1]]
        if not data:
            out.append(f"| {k} | - | - | no run of both arms has it |")
            continue
        mean, lo, hi = strat_boot([(x, y) for x, y in data])
        ma, mb = st.mean(st.mean(x) for x, _ in data), st.mean(st.mean(y) for _, y in data)
        out.append(f"| {k} | {mb:.2f} | {ma:.2f} | {mean:+.2f} ({lo:+.2f} to {hi:+.2f}) |")
    return out


def table(pairs: list[tuple[str, list[dict]]], allow_mixed: bool = False, compare: tuple[str, str] | None = None) -> str:
    problems = [p for t, rows in pairs if (p := check_hashes(t, rows))]
    if problems and not allow_mixed:
        raise SystemExit("refused, re-score first:\n  " + "\n  ".join(problems))
    dirty = [(t, [r["run"] for r in rows if contaminated(r)]) for t, rows in pairs]
    pairs = [(t, [r for r in rows if not contaminated(r)]) for t, rows in pairs]      # left out of every mean (#340)
    lines = ["| Ticket | Arm | Location given | Runs | Wall min | Turns | Context k | Output k | Cost $ | Search | devkb nav | Re-fetched | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |",
             "|" + "---|" * 18]
    per_arm: dict[str, list[dict]] = {}
    diffs: dict[str, dict[str, list[float]]] = {}
    for t, rows in pairs:
        arms = sorted({r["arm"] for r in rows}, key=lambda a: ORDER.index(a) if a in ORDER else 99)
        runs = {a: [per_run(r) for r in rows if r["arm"] == a] for a in arms}
        sums = {a: summary(runs[a]) for a in arms}
        for i, a in enumerate(arms):
            m, xs_rows = sums[a], runs[a]
            per_arm.setdefault(a, []).append(m)
            # the no-devkb arm given the ticket the same way: hidden against hidden, as filed against as filed (#337)
            base = base_for(a, arms, sums)
            vs = ""
            if base is not None and a not in NONE:
                dc, dk = 100 * (m["cost"] / base["cost"] - 1), 100 * (m["ctx"] / base["ctx"] - 1)
                noise = within_noise(m, base, "cost") and within_noise(m, base, "ctx")
                vs = f"cost {dc:+.0f}%, context {dk:+.0f}%" + (" (within noise)" if noise else "") + direction_note(m, base, dc, dk)
                diffs.setdefault(a, {"cost": [], "ctx": []})
                diffs[a]["cost"].append(m["cost"] - base["cost"])
                diffs[a]["ctx"].append(m["ctx"] - base["ctx"])
            flaky = f" ({m['flaky']} flaky)" if m.get("flaky") else ""       # green only on the re-run (#260)
            cut = f" ({m['cut_off']} cut off, cost left out)" if m.get("cut_off") else ""      # #303
            lines.append(f"| {('#' + t) if i == 0 else ''} | {a} | {'yes' if location_given(a) else 'no'} | {m['n']}{cut} | {fmt_range(m, 'wall')} | {m['turns']:.1f} | "
                         f"{fmt_range(m, 'ctx', 1e3, '', 0)} | {m['out'] / 1e3:.1f} | {fmt_range(m, 'cost', 1, '', 2)}{cv_note(m)} | {m['grep']:.1f} | {m['nav']:.1f} | {refetched(xs_rows)} | {m['own']:.1f} | "
                         f"{m['sub']:.1f} | {m['answers']:.1f} ({m['answer_chars']:.0f}) | {m['ok']}/{m['n']} | {m['suite']}/{m['n']}{flaky} | {vs} |")
    lines += ["", "| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |",
              "|---|---|---|---|---|---|"]
    for a, ms in per_arm.items():
        n = sum(m["n"] for m in ms)
        cost = sum(m["cost"] * m["n"] for m in ms) / n
        ctx = sum(m["ctx"] * m["n"] for m in ms) / n
        if a in diffs:
            lo, hi = bootstrap(diffs[a]["cost"])
            klo, khi = bootstrap(diffs[a]["ctx"])
            dc = f"${st.mean(diffs[a]['cost']):+.3f} (${lo:+.3f} to ${hi:+.3f})"
            dk = f"{st.mean(diffs[a]['ctx']) / 1e3:+.0f}k ({klo / 1e3:+.0f}k to {khi / 1e3:+.0f}k)"
        else:
            dc = dk = "—"
        lines.append(f"| {a} | {n} | ${cost:.2f} | {ctx / 1e3:.0f}k | {dc} | {dk} |")
    tickets = len([1 for _t, rows in pairs if rows])
    per_cell = sorted({sum(1 for x in rows if x["arm"] == a) for _t, rows in pairs for a in {r["arm"] for r in rows}})
    lines += ["", f"Repetition rule (#368, proposed): {tickets} ticket(s) pooled at {', '.join(map(str, per_cell))} run(s) per arm; "
              + (f"enough to pool ({MIN_POOLED_TICKETS} tickets needed)." if tickets >= MIN_POOLED_TICKETS else
                 f"**below n for a release claim: {MIN_POOLED_TICKETS} tickets are needed, this has {tickets}.** Read the intervals above as a direction at most.")]
    lines += start_section(pairs)
    lines += [f"WARNING #{t}: {len(rs)} run(s) changed the harness repository while they ran and are left out of the means: {', '.join(rs)} (#340)" for t, rs in dirty if rs]
    if problems:
        lines += ["", "Mixed hidden-check versions (allowed by flag): " + "; ".join(problems)]
    if compare:
        lines += compare_arms(pairs, *compare)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    allow = "--allow-mixed-checks" in argv
    compare = next((tuple(a.split("=", 1)[1].split(":")) for a in argv if a.startswith("--compare=")), None)    # --compare=ctxhid:rmainhid
    pairs = []
    for a in argv:
        if a.startswith("--"):
            continue
        t, f = a.split("=", 1)
        pairs.append((t, [json.loads(l) for l in open(B / f if not Path(f).is_absolute() else f) if l.strip()]))
    print(table(pairs, allow, compare))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
