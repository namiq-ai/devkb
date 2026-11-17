"""Does devkb help an agent on C#? Chain questions, plain agent against devkb agent (the C# twin of the C/C++ report,
bench/exercises/cpp/DEVKB-VALUE.md, same question, same columns).

  python bench/cs_value.py setup  WORK QUESTIONS.json      copy each repository for the devkb arm and `devkb init` it
                                                         (DEVKB_BIN=path/to/devkb: the installed release does it)
  python bench/cs_value.py run    WORK QUESTIONS.json [--reps 2] [--parallel 3] [--model sonnet]
  python bench/cs_value.py report WORK QUESTIONS.json OUT.md

QUESTIONS.json: [{"repo": "<path of a clean clone>", "target": "Type.Method", "name": "Method", "file": "...",
"truth": ["Type.Method", ...], "uncertain": [...], "tests": ["path", ...]}] as bench/cs_chain_truth.py prints them.

Arms. `plain`: the clean clone, Read/Glob/Grep and read-only shell, no MCP server. `devkb`: a copy with `devkb init`
(the AGENTS.md block, CLAUDE.md import and the MCP server in the lean-pack toolset) and the graph built by this
checkout's code; the same tools plus the devkb server. Same model, prompt, turn and budget caps for both.

Scoring (as for C/C++): method names in backticks, matched to the truth by method name (the truth's names are one
method family each, see cs_chain_truth.py). Precision = listed names in the truth / (in the truth + not in the truth
and not in its uncertain set); recall = truth names listed / truth; test files = truth test files named / truth test
files. Tool calls, turns, model calls and cost come from the stream-json transcript.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

PROMPT = ("List every production method that can reach `{target}` (defined in `{file}`), directly or indirectly, at any "
          "depth, and the test files that exercise it. This is read-only: do not modify any file. Name each method in "
          "backticks as `Type.Method`, and each test file by its path.")

READ_ONLY = ["Read", "Glob", "Grep", "Bash(grep:*)", "Bash(rg:*)", "Bash(find:*)", "Bash(ls:*)", "Bash(cat:*)",
             "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(sed -n:*)", "Bash(git log:*)", "Bash(git grep:*)"]
DENY = ["Edit", "Write", "NotebookEdit", "Task", "Bash(git push:*)", "WebFetch", "WebSearch"]


def short(repo: str) -> str:
    return Path(repo).name


def arm_dir(work: Path, repo: str, arm: str) -> Path:
    return Path(repo) if arm == "plain" else work / f"{short(repo)}-devkb"


# ── setup ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def setup(work: Path, qs: list[dict]) -> None:
    work.mkdir(parents=True, exist_ok=True)
    (work / "no-mcp.json").write_text(json.dumps({"mcpServers": {}}))
    for repo in sorted({q["repo"] for q in qs}):
        dst = arm_dir(work, repo, "devkb")
        if not dst.exists():
            shutil.copytree(repo, dst, symlinks=True)
        released = os.environ.get("DEVKB_BIN")          # the installed release (`devkb`), or this checkout's code
        if released:
            subprocess.run([released, "init", "--project", str(dst), "--toolset", "lean-pack"], check=True)
            cfg = {"mcpServers": {"devkb": {"command": released,
                                            "args": ["mcp", "--project", str(dst), "--toolset", "lean-pack"]}}}
        else:
            subprocess.run([PY, "-m", "devkb.cli", "init", "--project", str(dst), "--toolset", "lean-pack"], cwd=ROOT,
                           check=True, env=dict(os.environ, PYTHONPATH=str(ROOT)))
            # devkb init writes `devkb mcp` (the installed release): run this checkout's code instead
            cfg = {"mcpServers": {"devkb": {"command": PY, "args": ["-m", "devkb.cli", "mcp", "--project", str(dst),
                                                                    "--toolset", "lean-pack"],
                                            "env": {"PYTHONPATH": str(ROOT)}}}}
        (work / f"mcp-{short(repo)}.json").write_text(json.dumps(cfg))
        print("ready:", dst)


# ── run ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def run_one(work: Path, q: dict, arm: str, rep: int, model: str) -> Path:
    out = work / "runs" / f"{arm}-{short(q['repo'])}-{q['name']}-r{rep}.jsonl"
    if out.exists() and '"type":"result"' in out.read_text():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    cwd = arm_dir(work, q["repo"], arm)
    mcp = work / (f"mcp-{short(q['repo'])}.json" if arm == "devkb" else "no-mcp.json")
    allow = READ_ONLY + (["mcp__devkb"] if arm == "devkb" else [])
    # an ablation: DEVKB_DENY=uses,outline,symbol,search_docs denies those devkb tools (the agent keeps the rest)
    deny_devkb = [f"mcp__devkb__{t}" for t in os.environ.get("DEVKB_DENY", "").split(",") if t]
    cmd = ["claude", "-p", PROMPT.format(**q), "--model", model, "--output-format", "stream-json", "--verbose",
           "--max-turns", "60", "--max-budget-usd", "2", "--permission-mode", "dontAsk", "--strict-mcp-config",
           "--mcp-config", str(mcp), "--allowedTools", *allow, "--disallowedTools", *DENY, *deny_devkb]
    with open(out, "w") as f:
        subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=1800)
    return out


def preflight(work: Path, q: dict, model: str) -> bool:
    """The devkb arm's server must be connected and answer a pack, or the comparison means nothing."""
    cwd = arm_dir(work, q["repo"], "devkb")
    p = subprocess.run(["claude", "-p", f"Call the devkb pack tool for a refactor of `{q['name']}`; reply with its "
                        "first line only.", "--model", model, "--output-format", "stream-json", "--verbose",
                        "--max-turns", "4", "--strict-mcp-config", "--mcp-config",
                        str(work / f"mcp-{short(q['repo'])}.json"), "--allowedTools", "mcp__devkb"],
                       cwd=cwd, capture_output=True, text=True, timeout=600)
    conn = pack = False
    for line in p.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            conn = any(m["name"] == "devkb" and m["status"] == "connected" for m in e.get("mcp_servers", []))
        if e.get("type") == "user" and "Graph pack" in json.dumps(e):
            pack = True
    return conn and pack


def run(work: Path, qs: list[dict], reps: int, parallel: int, model: str) -> None:
    for repo in sorted({q["repo"] for q in qs}):
        q = next(x for x in qs if x["repo"] == repo)
        ok = preflight(work, q, model)
        print("preflight", short(repo), "ok" if ok else "FAILED")
        if not ok:
            raise SystemExit(3)
    jobs = [(q, arm, r) for r in range(1, reps + 1) for q in qs for arm in ("plain", "devkb")]
    with cf.ThreadPoolExecutor(parallel) as ex:
        for f in cf.as_completed([ex.submit(run_one, work, q, arm, r, model) for q, arm, r in jobs]):
            print("done", f.result().name)


# ── scoring and report ────────────────────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(ROOT / "bench" / "exercises" / "cpp"))


def classify(name: str, inp: dict) -> str:
    if name.startswith("mcp__") and "devkb" in name:
        return "devkb"
    if name == "Grep":
        return "grep"
    if name == "Read":
        return "file load"
    if name == "Glob":
        return "find/list"
    if name == "Bash":
        cmd = (inp.get("command") or "").strip()
        first = re.split(r"\s*(?:&&|\|\||;|\|)\s*", cmd)[0]
        if re.search(r"\b(grep|rg|ag|git grep)\b", cmd):
            return "grep"
        if re.match(r"(cat|sed|head|tail|less|awk|nl)\b", first):
            return "file load"
        if re.match(r"(find|ls|tree|wc)\b", first):
            return "find/list"
        return "other shell"
    return "other"


def stream_stats(path: Path) -> dict:
    turns = cost = 0
    msgs, calls, size, uses, result = set(), {}, {}, {}, ""
    best: dict[str, float] = {}
    for line in path.read_text().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            if e["message"].get("id"):
                msgs.add(e["message"]["id"])
            for x in e["message"].get("content", []):
                if x.get("type") == "tool_use":
                    k = classify(x["name"], x.get("input") or {})
                    uses[x["id"]] = k
                    calls[k] = calls.get(k, 0) + 1
        if e.get("type") == "user" and isinstance(e["message"].get("content"), list):
            for x in e["message"]["content"]:
                if x.get("type") == "tool_result" and x.get("tool_use_id") in uses:
                    c = x.get("content")
                    k = uses[x["tool_use_id"]]
                    size[k] = size.get(k, 0) + len(c if isinstance(c, str) else json.dumps(c))
        if e.get("type") == "result":
            turns += e.get("num_turns", 0)
            cost = max(cost, e.get("total_cost_usd", 0) or 0)
            result = e.get("result") or result
            for u in (e.get("modelUsage") or {}).values():
                for k, v in u.items():
                    if isinstance(v, (int, float)):
                        best[k] = max(best.get(k, 0), v)
    ctx = best.get("inputTokens", 0) + best.get("cacheCreationInputTokens", 0) + best.get("cacheReadInputTokens", 0)
    return {"turns": turns, "msgs": len(msgs), "cost": cost, "calls": calls, "size": size, "result": result,
            "ctx": ctx, "out": best.get("outputTokens", 0)}


def score(q: dict, text: str) -> dict:
    names = set()
    for tok in re.findall(r"`([^`\n]{1,200})`", text):
        tok = re.sub(r"\(.*$", "", tok).strip()
        tok = re.sub(r"<[^<>]*>", "", tok)
        last = re.split(r"\.|::", tok)[-1].strip()
        if re.match(r"^[A-Za-z_]\w*$", last) and not tok.endswith((".cs", "/")):
            names.add(last)
    truth = {t.split(".")[-1] for t in q["truth"]}
    unsure = {t.split(".")[-1] for t in q.get("uncertain", [])} | {q["name"]}
    if q.get("production_methods"):
        # only names the compiler knows as production methods count: a type named in prose, a test method listed
        # under the tests, a .NET method are neither right nor wrong
        names &= set(q["production_methods"]) | truth
    listed = names - {q["name"]}
    right, wrong = listed & truth, listed - truth - unsure
    tests = q.get("tests", [])
    named = [t for t in tests if t in text or Path(t).name in text]
    return {"listed": len(listed), "right": len(right), "wrong": len(wrong),
            "P": len(right) / (len(right) + len(wrong)) if right or wrong else None,
            "R": len(right) / len(truth) if truth else None,
            "T": len(named) / len(tests) if tests else None, "wrong_names": sorted(wrong)[:12],
            "missed": sorted(truth - listed)[:12]}


def report(work: Path, qs: list[dict], out_md: Path) -> None:
    rows, per_run = [], []
    tot: dict[str, list] = {"plain": [], "devkb": []}
    for q in qs:
        for arm in ("plain", "devkb"):
            runs = sorted((work / "runs").glob(f"{arm}-{short(q['repo'])}-{q['name']}-r*.jsonl"))
            got = []
            for p in runs:
                st = stream_stats(p)
                if not st["result"]:
                    continue
                sc = score(q, st["result"])
                got.append((p, st, sc))
                per_run.append((short(q["repo"]), q["target"], arm, p.stem.rsplit("-", 1)[-1], st, sc))
            if got:
                rows.append((q, arm, got))
                tot[arm].extend(got)

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return statistics.mean(xs) if xs else None

    def f2(x):
        return "" if x is None else f"{x:.2f}"

    def tool(got, k):
        c = mean([g[1]["calls"].get(k, 0) for g in got]) or 0
        s = mean([g[1]["size"].get(k, 0) for g in got]) or 0
        return "0" if not c else f"{c:.1f} ({s / 1000:.1f}k)"

    def line(label, arm, got, truth="", listed=""):
        return (f"| {label} | {arm} | {truth} | {listed} | {f2(mean([g[2]['P'] for g in got]))} | "
                f"{f2(mean([g[2]['R'] for g in got]))} | {f2(mean([g[2]['T'] for g in got]))} | "
                f"{mean([g[1]['turns'] for g in got]):.1f} | {mean([g[1]['msgs'] for g in got]):.1f} | "
                f"${mean([g[1]['cost'] for g in got]):.3f} | {tool(got, 'grep')} | {tool(got, 'file load')} | "
                f"{tool(got, 'devkb')} |")

    L = []
    w = L.append
    n = sum(len(g) for _, _, g in rows)
    w("# Does devkb help an agent on C#? Chain questions, scored against the compiler\n")
    w(f"Exploratory: {len(qs)} questions, {len({q['repo'] for q in qs})} repositories, {n} runs, one model, one session. "
      "The C# counterpart of `bench/exercises/cpp/DEVKB-VALUE.md`.\n")
    w("## Setup\n")
    w("- **Question** (read-only): \"List every production method that can reach `F`, directly or indirectly, at any "
      "depth, and the test files that exercise it.\"")
    if all(q.get("truth_source") == "roslyn" for q in qs):
        w("- **Truth**: the compiler. `bench/roslyn_truth` (Roslyn's semantic model over each repository restored with "
          "the .NET SDK it pins) runs on GitHub's runners (`.github/workflows/cs-truth.yml`); "
          "`bench/cs_truth_from_roslyn.py` takes the production methods that reach `F` through statically bound calls. "
          "Methods that reach it only through virtual or interface dispatch, and callers in benchmark, sample or "
          "snippet code, score neither right nor wrong. Production = not a test, benchmark, sample, snippet or example. "
          "Questions were picked from the compiler graph (`bench/cs_pick_from_roslyn.py`) or kept from the text picker "
          "(`bench/cs_chain_truth.py`) only where the compiler confirmed production callers.")
    else:
        w("- **Truth**: `bench/cs_chain_truth.py`: the text-visible call graph, production code only; names on an exact "
          "path are one method family each; methods reached through an ambiguous name are uncertain.")
    w("- **Arms**: `plain` (Read, Glob, Grep, read-only shell; no MCP server) and `devkb` (the same tools plus the MCP "
      "server in `lean-pack` mode and the AGENTS.md block `devkb init` writes), graph built by the C# round-3 code. "
      "The devkb server was proven connected (a pack call answered) before the runs. Model: Sonnet, both arms; "
      "60-turn and $2 caps.")
    w("- **Scoring**: method names in backticks that the compiler knows as production methods, matched to the truth by "
      "name (a type named in prose or a test method listed with the tests is neither right nor wrong). Recall is "
      "solid; precision is approximate where two methods share a name.\n")
    w("## Result\n")
    w("| Question | Arm | Truth | Listed | Precision | Recall | Test files | Turns | Model calls | Cost | Grep | "
      "File load | devkb |")
    w("|" + "---|" * 13)
    for q, arm, got in rows:
        label = f"{short(q['repo'])} `{q['target']}`" if arm == "plain" else ""
        w(line(label, arm, got, str(len(q["truth"])), f"{mean([g[2]['listed'] for g in got]):.0f}"))
    for arm in ("plain", "devkb"):
        if tot[arm]:
            w(line(f"**All {len(tot[arm])} runs**", f"**{arm}**", tot[arm]))
    w("\nCalls per run (mean); parentheses give the text returned to the model. Grep = the Grep tool or a shell grep, "
      "file load = Read or shell cat/sed/head. Truth is the number of exact production callers; Listed is how many "
      "methods the agent named.\n")
    w("Per run:\n")
    w("| Repo | Question | Arm | Run | Turns | Model calls | Cost | Precision | Recall | Wrong names | Missed |")
    w("|" + "---|" * 11)
    for repo, tgt, arm, rep, st, sc in per_run:
        w(f"| {repo} | {tgt.split('.')[-1]} | {arm} | {rep} | {st['turns']} | {st['msgs']} | ${st['cost']:.3f} | "
          f"{f2(sc['P'])} | {f2(sc['R'])} | {', '.join(sc['wrong_names'][:4])} | {', '.join(sc['missed'][:4])} |")
    w("")
    if tot["plain"] and tot["devkb"]:
        mp = statistics.median([g[1]["cost"] for g in tot["plain"]])
        md = statistics.median([g[1]["cost"] for g in tot["devkb"]])
        w(f"All plain runs against all devkb runs: median cost ${mp:.3f} against ${md:.3f} "
          f"({(md - mp) / mp:+.0%}).\n")
    out_md.write_text("\n".join(L) + "\n")
    print(out_md.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("setup", "run", "report"))
    ap.add_argument("work")
    ap.add_argument("questions")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()
    work, qs = Path(a.work), json.loads(Path(a.questions).read_text())
    if a.cmd == "setup":
        setup(work, qs)
    elif a.cmd == "run":
        run(work, qs, a.reps, a.parallel, a.model)
    else:
        report(work, qs, Path(a.out or work / "DEVKB-VALUE-CSHARP.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
