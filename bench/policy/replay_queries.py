"""Replay the devkb queries agents made in recorded runs against the graph of the ticket's base commit, and judge each
answer by what the agent worked in afterwards (the files it edited or read after the query, in that run).

Free and deterministic: no model runs. It answers "did the graph point at the code the agent needed?" for a graph or
ranking change, before any live batch is paid for.

Usage: replay_queries.py extract OUT.json          queries and per-run working sets from bench/policy/runs
       replay_queries.py run OUT.json [--devkb BIN] [--keep DIR] [--context]   replay them, print the table
The base graphs are built once under --keep (default ~/.cache/devkb/replay), from each ticket's initial commit in a run checkout."""
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = Path.home() / ".cache" / "devkb" / "policy-work"
TICKETS = tuple(os.environ.get("REPLAY_TICKETS", "118,120,203,205").split(","))   # REPLAY_TICKETS=301,302,... for a held-out set
sys.path.insert(0, str(HERE))
import storybench as sb  # noqa: E402

QUERY = re.compile(r"(?:\S*/)?devkb\s+(symbol|outline|uses|pack|docs)\b([^;&|\n]*)")


def rel(path: str, run: str) -> str:
    p = path.replace(str(WORK / run) + "/", "")
    return p.lstrip("./")


def extract(out: Path) -> None:
    rows, prompts = [], {}
    for f in sorted((HERE / "runs").glob("p*-*-r*/stream.jsonl")):
        m = re.match(r"p(\d+)-(\w+)-r(\d+)", f.parent.name)
        if not m or m[1] not in TICKETS or "none" in m[2]:
            continue
        run, calls = f.parent.name, []
        key = (m[1], m[2])                                              # the prompt is not in the stream: rebuild it as the harness did
        if key not in prompts:
            import policybench as pb  # noqa: PLC0415
            prompts[key] = pb.run_prompt(m[1], m[2], WORK / run)
        prompt = prompts[key]
        for line in open(f):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") != "assistant":
                continue
            for b in e["message"].get("content", []):
                if b.get("type") == "tool_use":
                    calls.append((b["name"], b.get("input") or {}))
        for i, (name, inp) in enumerate(calls):
            if name != "Bash":
                continue
            for seg in re.split(r"&&|;|\n", inp.get("command", "") or ""):
                q = QUERY.search(seg.split("|")[0])
                if not q or "--project" in seg and re.search(r"--project\s+\S*corpus", seg):
                    continue
                after = set()
                for nm, ip in calls[i:]:
                    if nm in ("Edit", "Write", "MultiEdit", "Read"):
                        after.add(rel(str(ip.get("file_path", "")), run))
                    elif nm == "Bash":
                        after.update(rel(x, run) for x in re.findall(r"[\w./-]+\.(?:py|h|cc|cpp|ts|md)\b", ip.get("command", "") or ""))
                edited = {rel(str(ip.get("file_path", "")), run) for nm, ip in calls if nm in ("Edit", "Write", "MultiEdit")}
                rows.append({"run": run, "ticket": m[1], "arm": m[2], "kind": q[1], "args": q[2].strip(), "after": sorted(after),
                             "edited": sorted(edited), "index": i, "prompt": prompt[:8000]})
    out.write_text(json.dumps(rows, indent=1))
    print(len(rows), "queries from", len({r["run"] for r in rows}), "runs")


def base_graph(ticket: str, keep: Path, devkb: str) -> Path:
    d = keep / f"t{ticket}"
    if (d / ".devkb" / "nodes.jsonl").exists():
        return d
    run = next(p for p in sorted([*WORK.glob(f"p{ticket}-rmain-r*"), *WORK.glob(f"p{ticket}-main-r*")]))
    first = subprocess.run(["git", "-C", str(run), "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True).stdout.split()[0]
    d.mkdir(parents=True, exist_ok=True)
    arc = subprocess.run(["git", "-C", str(run), "archive", first], capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(d)], input=arc, check=True)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.name=r", "-c", "user.email=r@e.x", "commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(d), *c], capture_output=True)
    subprocess.run([devkb, "build", "--project", str(d)], capture_output=True)
    return d


FIRST = re.compile(r"^\s*1\.\s+(\S+)", re.M)
LISTED = re.compile(r"^\s*\d+\.\s+(\S+)\s+\S+\s+L(\d+)", re.M)
_CHANGED: dict[str, set] = {}


def changed_symbols(run: str, ticket: str, keep: Path, devkb: str) -> set[tuple[str, int]]:
    """(file, first line) of every definition at the ticket's base that the run changed: the old-side line ranges of the run's diff
    (committed or not) against its first commit, mapped onto the base graph's definitions. This is the function-level truth: the
    file-level judge credits a first match that sits in a file the agent edited even when the agent never touched that function."""
    if run not in _CHANGED:
        w = WORK / run
        first = subprocess.run(["git", "-C", str(w), "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True).stdout.split()
        out: set = set()
        if first:
            from devkb.process_api import ProcessAPI  # noqa: PLC0415
            from devkb.read_tools import ReadTools  # noqa: PLC0415
            tools = ReadTools(ProcessAPI(str(base_graph(ticket, keep, devkb))))
            diff = subprocess.run(["git", "-C", str(w), "diff", "--unified=0", first[0]], capture_output=True, text=True).stdout
            f = None
            for line in diff.splitlines():
                if line.startswith("--- "):
                    f = line[6:] if line.startswith("--- a/") else None
                m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
                if f and m:
                    a, n = int(m[1]), int(m[2]) if m[2] is not None else 1
                    for i in tools.ids:
                        ps = tools.idx.props[i]
                        ls, le = ps.get("line_start"), ps.get("line_end")
                        if tools.file[i] == f and ls and le and (a <= le and a + max(n, 1) - 1 >= ls):
                            out.add((f, int(ls)))
        _CHANGED[run] = out
    return _CHANGED[run]


def judge(r: dict, out: str, fn: set | None = None) -> dict:
    """symbol: the first-listed file is one the agent worked in. uses/pack: a listed file is. outline: ok when it answered."""
    files = set(re.findall(r"[\w./-]+\.(?:py|h|cc|cpp|ts|md)", out))
    work = set(r["after"])
    j = {"chars": len(out), "empty": bool(re.search(r"no match|cannot resolve|not found", out[:300], re.I)) and len(out) < 700}
    if r["kind"] == "symbol":
        m = FIRST.search(out)
        top = m[1] if m else None
        n = re.search(r"(\d+) match", out)
        listed = re.findall(r"^\s*\d+\.\s+(\S+)", out, re.M)
        rank = next((k + 1 for k, x in enumerate(listed) if x in work), 0)
        defs = [(m[1], int(m[2])) for m in LISTED.finditer(out)]
        frank = next((k + 1 for k, d in enumerate(defs) if d in fn), 0)         # function level: a definition the run changed
        j.update(top=top, matches=int(n[1]) if n else 0, hit=bool(top and top in work), answered=bool(top), rank=rank,
                 listed=bool(rank), fn_hit=frank == 1, fn_rank=frank)
    elif r["kind"] in ("uses", "pack"):
        j.update(hit=bool(files & work), answered=not j["empty"] and bool(files))
    else:
        j.update(hit=not j["empty"], answered=not j["empty"])
    return j


def run(inp: Path, devkb: str, keep: Path, use_context: bool = False) -> list[dict]:
    rows = json.loads(inp.read_text())
    res = []
    for r in rows:
        d = base_graph(r["ticket"], keep, devkb)
        (d / ".devkb" / "session-context.json").unlink(missing_ok=True)
        if use_context:                                                # what the prompt hook would have recorded for this run
            sys.path.insert(0, str(REPO))
            from devkb import session_context  # noqa: PLC0415
            session_context.record(d, r["prompt"])
        cmd = f"{devkb} {r['kind']} {r['args']}"
        cmd = re.sub(r"--project\s+\S+", "", cmd) + f" --project {d}"
        cmd = re.sub(r"^\S*devkb", devkb, cmd.replace(".venv/bin/devkb", devkb))
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=d, timeout=120)
        res.append({**r, **judge(r, p.stdout + p.stderr, changed_symbols(r["run"], r["ticket"], keep, devkb)), "cmd": cmd.replace(str(d), "<t>")[:140]})
    return res


def table(res: list[dict]) -> str:
    """Per recorded query and per DISTINCT query (the same ticket, kind and arguments counted once: one popular query run by many
    agents is one query), file-level and function-level."""
    def norm(r):
        return (r["ticket"], r["kind"], re.sub(r"--\S+(?:\s+\S+)?|[|].*", "", r["args"].replace("--project .", "")).strip().strip("\"'"))
    g = defaultdict(list)
    for r in res:
        g[r["kind"]].append(r)
    lines = ["| queries | recorded | distinct | answered | top-1 file on target | top-1 definition changed | listed anywhere (file) | median chars |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(g):
        v = g[k]
        dist = {}
        for r in v:
            dist.setdefault(norm(r), []).append(r)
        ch = sorted(x["chars"] for x in v)[len(v) // 2]
        fnn = [x for x in v if "fn_hit" in x]
        lines.append(f"| {k} | {len(v)} | {len(dist)} | {sum(x['answered'] for x in v)} | {sum(x['hit'] for x in v)} "
                     f"({100 * sum(x['hit'] for x in v) // len(v)}%) | {(str(sum(x['fn_hit'] for x in fnn)) + f' of {len(fnn)}') if fnn else '-'} | "
                     f"{sum(x.get('listed', x['hit']) for x in v)} | {ch} |")
    sym = [r for r in res if r["kind"] == "symbol"]
    by_dist: dict = {}
    for r in sym:
        by_dist.setdefault(norm(r), []).append(r)
    lines += ["", f"symbol queries: {len(sym)} recorded, {len(by_dist)} distinct; the largest group is {max(len(x) for x in by_dist.values())} runs of one query "
              f"({max(by_dist, key=lambda k: len(by_dist[k]))[2]!r} on #{max(by_dist, key=lambda k: len(by_dist[k]))[0]}).",
              f"per distinct query, top-1 file on target {sum(any(x['hit'] for x in v) for v in by_dist.values())} of {len(by_dist)}; "
              f"top-1 definition changed {sum(any(x.get('fn_hit') for x in v) for v in by_dist.values())} of {len(by_dist)}"]
    return "\n".join(lines)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("extract", "run"):
        raise SystemExit(__doc__)
    if a[0] == "extract":
        extract(Path(a[1]))
    else:
        bin_ = a[a.index("--devkb") + 1] if "--devkb" in a else str(REPO / ".venv" / "bin" / "devkb")
        keep = Path(a[a.index("--keep") + 1]) if "--keep" in a else Path.home() / ".cache" / "devkb" / "replay"
        ctx = "--context" in a
        res = run(Path(a[1]), bin_, keep, ctx)
        Path(a[1]).with_suffix(".context.result.json" if ctx else ".result.json").write_text(json.dumps(res, indent=1))
        print(table(res))
