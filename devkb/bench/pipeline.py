#!/usr/bin/env python3
"""The benchmark pipeline: one repository from bench/repos.yaml, from a pinned clone to a report.

  python3 -m devkb.bench.pipeline list
  python3 -m devkb.bench.pipeline prepare ID [--work bench-work]   clone, graph, tasks, packs, pack check (no model)
  python3 -m devkb.bench.pipeline run ID --arms plain,core,lean,pack --reps 5 --model sonnet   agent runs (paid)
  python3 -m devkb.bench.pipeline report ID                        cost and quality per arm, against plain

prepare is free and deterministic: the same entry gives the same graph, tasks, truth and packs. Its pack check scores
each pack as if it were an answer, against the truth computed from source, so a repository where the graph is wrong is
visible before any money is spent. run drives the Claude Code CLI (`claude` on PATH, authenticated) with the same
harness, arms and protocol as the study: every arm in one shuffled session, a discarded warm-up per arm.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "bench" / "repos.yaml"
BENCH = Path(__file__).resolve().parent
ID_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
KINDS = ("web", "cli")


def registry() -> dict[str, dict]:
    entries = (yaml.safe_load(REGISTRY.read_text()) or {}).get("repos", [])
    out = {}
    for e in entries:
        problems = [k for k in ("id", "url", "commit", "kind", "seed", "per_kind") if k not in e]
        if problems:
            raise SystemExit(f"bench/repos.yaml: entry {e.get('id', '?')} lacks {problems}")
        if not ID_RX.match(str(e["id"])) or e["id"] in out:
            raise SystemExit(f"bench/repos.yaml: bad or duplicate id {e['id']!r}")
        if not re.fullmatch(r"[0-9a-f]{40}", str(e["commit"])):
            raise SystemExit(f"bench/repos.yaml: {e['id']}: commit must be a full 40-character hash")
        if e["kind"] not in KINDS:
            raise SystemExit(f"bench/repos.yaml: {e['id']}: kind must be one of {KINDS}")
        if not (str(e["url"]).startswith("https://") or e["url"] == "self"):
            raise SystemExit(f"bench/repos.yaml: {e['id']}: url must be https, or `self` for this repository")
        out[e["id"]] = e
    return out


def sh(*cmd: str, cwd: Path | None = None, env: dict | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env={**os.environ, **(env or {})})


def paths(work: Path, rid: str) -> dict[str, Path]:
    d = work / rid
    return {"dir": d, "checkout": d / "checkout", "graph": d / "graph", "tasks": d / "tasks.json",
            "packs": d / "tasks.packs.json", "check": d / "pack-check.json", "runs": d / f"{rid}.jsonl",
            "report": d / "report.json"}


def prepare(e: dict, work: Path) -> int:
    p = paths(work, e["id"])
    p["dir"].mkdir(parents=True, exist_ok=True)
    if not (p["checkout"] / ".git").exists():
        sh("git", "init", "-q", str(p["checkout"]))
        # `self`: devkb measured on its own repository, fetched from this checkout (no token needed in CI)
        sh("git", "remote", "add", "origin", str(ROOT) if e["url"] == "self" else e["url"], cwd=p["checkout"])
    sh("git", "fetch", "-q", "origin", e["commit"], cwd=p["checkout"])
    sh("git", "checkout", "-q", "--force", e["commit"], cwd=p["checkout"])
    sh("git", "clean", "-qfdx", cwd=p["checkout"])
    py = sys.executable
    # The graph is built into the snapshot folder, never into the checkout the agents will search.
    env = {"DEVKB_DIR": str(p["graph"])}
    if p["graph"].exists():
        shutil.rmtree(p["graph"])
    sh(py, "-m", "devkb.cli", "build", "--project", str(p["checkout"]), env=env)
    gen = "confirm_tasks.py" if e["kind"] == "web" else "cli_tasks.py"
    sh(py, str(BENCH / gen), str(p["checkout"]), str(p["tasks"]), "--seed", str(e["seed"]),
       "--per-kind", str(e["per_kind"]), "--prefix", f"{e['id']}-")
    tasks = json.loads(p["tasks"].read_text())
    if not tasks:
        print(f"{e['id']}: the generator found no task that meets its selection rules", file=sys.stderr)
        return 1
    sh(py, str(BENCH / "add_packs.py"), str(p["checkout"]), str(p["tasks"]), str(p["packs"]),
       env={"DEVKB_DIR": str(p["graph"]), "DEVKB_REPO": str(p["checkout"])})
    check = pack_check(json.loads(p["packs"].read_text()))
    # The pack check compares the pack with the truth; a blind spot both share scores 1.0. A second implementation
    # of the refactor truth, sharing no code with either, catches that before any run is paid for.
    sys.path.insert(0, str(BENCH))
    import truth_check  # noqa: PLC0415
    rows = truth_check.check(p["checkout"], json.loads(p["packs"].read_text()))
    check["truth_check"] = rows
    check["summary"]["truth_missing_callers"] = {r["task"]: r["missing"] for r in rows if r["missing"]}
    p["check"].write_text(json.dumps(check, indent=1))
    print(json.dumps(check["summary"], indent=1))
    if check["summary"]["truth_missing_callers"]:
        print(f"{e['id']}: the truth misses callers an independent check proves (pack-check.json, truth_check); "
              "fix the truth before running agents", file=sys.stderr)
        return 1
    return 0


SECTION = re.compile(r"^## (.+?)(?: \(.*)?$", re.M)


def _sections(pack: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    parts = SECTION.split(pack)
    for title, body in zip(parts[1::2], parts[2::2]):
        out[title.strip()] = re.findall(r"^- `([^`]+)`", body, re.M)
    return out


def _short(k: str) -> str:
    return k.split("::")[0] + "::" + k.split("::")[1].split(".")[-1] if "::" in k else k


def pack_check(tasks: list[dict]) -> dict:
    """Each pack read as an answer and scored with the harness's own scorer against the truth from source."""
    sys.path.insert(0, str(BENCH))
    import workflow_run as wr  # noqa: PLC0415

    rows = []
    for t in tasks:
        s = _sections(t["pack"])
        if t["kind"] == "refactor":
            ans = {"caller_files": s.get("Files with a direct caller", []), "test_files": s.get("Test files among them", [])}
        elif t["kind"] in ("rca", "err_to_handler"):
            ans = {"raiser": _short((s.get("Raised by") or [""])[0]),
                   "callers": [_short(x) for x in s.get("Functions that reach it, at any depth", [])],
                   "handlers": [_short(x) for x in s.get("Route handlers that reach it", [])],
                   "test_files": s.get("Test files on those paths", [])}
        elif t["kind"] == "impact":
            ans = {"handlers": [_short(x) for x in s.get("Route handlers that reach it", [])],
                   "test_files": [x for x in s.get("Test files to run", [])]}
        else:
            continue
        sc = wr.score(t, json.dumps(ans))
        rows.append({"task": t["id"], "kind": t["kind"], "score": sc["score"], "parts": sc["parts"],
                     "complete": "**Complete.**" in t["pack"], "words": len(t["pack"].split())})
    kinds = sorted({r["kind"] for r in rows})
    summary = {"tasks": len(rows), "mean_score": round(sum(r["score"] for r in rows) / max(len(rows), 1), 3),
               "by_kind": {k: round(sum(r["score"] for r in rows if r["kind"] == k) / sum(1 for r in rows if r["kind"] == k), 3) for k in kinds},
               "complete_but_wrong": [r["task"] for r in rows if r["complete"] and r["score"] < 1.0]}
    return {"summary": summary, "tasks": rows}


def run(e: dict, work: Path, arms: str, reps: int, model: str, workers: int) -> int:
    p = paths(work, e["id"])
    if not p["packs"].exists():
        raise SystemExit(f"run `prepare {e['id']}` first")
    if shutil.which("claude") is None:
        raise SystemExit("the Claude Code CLI (`claude`) is not on PATH")
    sh(sys.executable, str(BENCH / "workflow_run.py"), str(p["packs"]), str(p["runs"]), "--reps", str(reps),
       "--workers", str(workers), "--seed", str(e["seed"]),
       env={"BENCH_CHECKOUT": str(p["checkout"]), "BENCH_GRAPH": str(p["graph"]), "BENCH_PROJECT": str(p["checkout"]),
            "BENCH_MODEL": model, "BENCH_ARMS": arms, "BENCH_MAX_TURNS": "40", "BENCH_TOOL_ROOT": str(ROOT)})
    return 0


ARM_ORDER = ("plain", "core", "workflow", "lean", "pack")


def token_table(rows: list[dict]) -> str:
    """Per arm, the median run's tokens by kind, and the task-weighted change in context processed against plain.

    input        uncached input tokens            cache write  context written to the prompt cache (first use, or a
    cache read   context served from the cache                 miss or expiry: the context sent again)
    output       generated tokens (thinking included)          context      input + cache write + cache read
    initial ctx  context given to the first model call: system prompt, tool definitions, task, pack
    peak ctx     the largest context any model call was given
    Runs recorded before these fields existed show input and cache write combined (fresh - output)."""
    import collections  # noqa: PLC0415
    import statistics as st  # noqa: PLC0415

    full = all("cache_write" in r for r in rows)

    def ctx(r):
        return r.get("input", 0) + r.get("cache_write", 0) + r["cache_read"] if "cache_write" in r else r["fresh"] - r["output"] + r["cache_read"]

    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by[r["arm"]][r["task"]].append(r)
    arms = [a for a in ARM_ORDER if a in by]
    tasks = [t for t in by.get("plain", {}) if all(t in by[a] for a in arms)]
    base = sum(st.mean(ctx(r) for r in by["plain"][t]) for t in tasks) if "plain" in by and tasks else 0
    cols = (["cost $", "turns", "model calls", "initial ctx", "peak ctx", "input", "cache write", "cache read", "output",
             "thinking"] if full else ["cost $", "turns", "input + cache write", "cache read", "output"]) + ["context", "context saved vs plain"]
    out = ["| arm | runs | " + " | ".join(cols) + " |", "|---|---:|" + "---:|" * len(cols)]
    for a in arms:
        rs = [r for t in by[a].values() for r in t]
        med = lambda f: st.median(f(r) for r in rs)  # noqa: E731
        vals = [f"{med(lambda r: r['cost'] or 0):.4f}", f"{med(lambda r: r['turns'] or 0):g}"]
        if full:
            vals += [f"{med(lambda r: r['model_calls']):g}", f"{med(lambda r: r['ctx_initial']):,.0f}",
                     f"{med(lambda r: r['ctx_peak']):,.0f}", f"{med(lambda r: r['input']):,.0f}",
                     f"{med(lambda r: r['cache_write']):,.0f}", f"{med(lambda r: r['cache_read']):,.0f}",
                     f"{med(lambda r: r['output']):,.0f}", f"{med(lambda r: r['thinking']):,.0f}"]
        else:
            vals += [f"{med(lambda r: r['fresh'] - r['output']):,.0f}", f"{med(lambda r: r['cache_read']):,.0f}",
                     f"{med(lambda r: r['output']):,.0f}"]
        vals.append(f"{med(ctx):,.0f}")
        if base and a != "plain":
            vals.append(f"{1 - sum(st.mean(ctx(r) for r in by[a][t]) for t in tasks) / base:+.0%}")
        else:
            vals.append("—")
        out.append(f"| {a} | {len(rs)} | " + " | ".join(vals) + " |")
    return "\n".join(out)


def detail_table(rows: list[dict]) -> str:
    """Per task: median cost, mean score and median turns in each arm; then the mean of each score part per task kind
    and arm (which part of the answer an arm got wrong), and the graph tools each arm called."""
    import collections  # noqa: PLC0415
    import statistics as st  # noqa: PLC0415

    by = collections.defaultdict(list)
    for r in rows:
        by[(r["task"], r["arm"])].append(r)
    arms = [a for a in ARM_ORDER if any(r["arm"] == a for r in rows)]
    tasks = sorted({(r["kind"], r["task"]) for r in rows})
    out = ["Per task: median cost $ / mean score / median turns.", "",
           "| kind | task | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
    for kind, t in tasks:
        cells = []
        for a in arms:
            rs = by.get((t, a), [])
            cells.append(f"{st.median((r['cost'] or 0) for r in rs):.3f} / {st.mean(r['score'] for r in rs):.2f} / "
                         f"{st.median((r['turns'] or 0) for r in rs):g}" if rs else "—")
        out.append(f"| {kind} | {t} | " + " | ".join(cells) + " |")
    out += ["", "Mean of each score part:", ""]
    for kind in sorted({k for k, _ in tasks}):
        parts = sorted({p for r in rows if r["kind"] == kind for p in (r.get("parts") or {})})
        out += [f"| {kind} | " + " | ".join(parts) + " | runs |", "|---|" + "---:|" * (len(parts) + 1)]
        for a in arms:
            rs = [r for r in rows if r["kind"] == kind and r["arm"] == a]
            if rs:
                out.append(f"| {a} | " + " | ".join(
                    f"{st.mean((r.get('parts') or {}).get(p, 0) for r in rs):.2f}" for p in parts) + f" | {len(rs)} |")
        out.append("")
    out += ["Graph tools called (all runs):", ""]
    for a in arms:
        c = collections.Counter(t for r in rows if r["arm"] == a for t in (r.get("graph_tools") or []))
        total = sum((r["cost"] or 0) for r in rows if r["arm"] == a)
        used = ", ".join(f"`{k}` {v}" for k, v in c.most_common()) or "none"
        out.append(f"- **{a}**: ${total:.2f} in all; {used}")
    return "\n".join(out)


def report(e: dict, work: Path, model: str) -> int:
    p = paths(work, e["id"])
    sh(sys.executable, str(ROOT / "study" / "analysis" / "analyze.py"), str(p["runs"]), "--model", model,
       "--out", str(p["report"]))
    r = json.loads(p["report"].read_text())
    print(f"\n{e['id']}: {r['runs']} runs, {r['tasks']} tasks, ${r['cost_usd']}")
    for arm, x in r["pooled"].items():
        c, q = x["cost"], x["quality"]
        print(f"  {arm:9s} saved {c['saved']:+.0%} [{c['lo']:+.0%}, {c['hi']:+.0%}]  quality {q['diff']:+.3f} "
              f"[{q['lo']:+.3f}, {q['hi']:+.3f}]")
    rows = [json.loads(x) for x in p["runs"].read_text().splitlines() if x.strip()]
    print("\nTokens by kind (median run):\n" + token_table(rows))
    print("\n" + detail_table(rows))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("list", "prepare", "run", "report", "tokens", "detail"))
    ap.add_argument("id", nargs="?")
    ap.add_argument("--work", default=os.environ.get("BENCH_WORK", "bench-work"))
    ap.add_argument("--arms", default="plain,core,lean,pack")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--runs", nargs="+", help="tokens: runs files to tabulate")
    a = ap.parse_args()
    if a.command in ("tokens", "detail"):
        rows = [json.loads(x) for f in a.runs for x in Path(f).read_text().splitlines() if x.strip()]
        print(token_table(rows) if a.command == "tokens" else detail_table(rows))
        return 0
    reg = registry()
    if a.command == "list":
        for e in reg.values():
            print(f"{e['id']:16s} {e['kind']:4s} {e['commit'][:10]}  {e['url']}")
        return 0
    if a.id not in reg:
        raise SystemExit(f"unknown id {a.id!r}; see bench/repos.yaml")
    work = Path(a.work).resolve()
    e = reg[a.id]
    if a.command == "prepare":
        return prepare(e, work)
    if a.command == "run":
        return run(e, work, a.arms, a.reps, a.model, a.workers)
    return report(e, work, a.model)


if __name__ == "__main__":
    raise SystemExit(main())
