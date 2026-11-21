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


def judge(r: dict, out: str) -> dict:
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
        j.update(top=top, matches=int(n[1]) if n else 0, hit=bool(top and top in work), answered=bool(top), rank=rank,
                 listed=bool(rank))
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
        res.append({**r, **judge(r, p.stdout + p.stderr), "cmd": cmd.replace(str(d), "<t>")[:140]})
    return res


def table(res: list[dict]) -> str:
    g = defaultdict(list)
    for r in res:
        g[r["kind"]].append(r)
        g["ALL"].append(r)
        g[("hidden " if r["arm"].endswith("hid") else "as filed ") + r["kind"]].append(r)
    lines = ["| queries | n | answered | top-1 on target | listed anywhere | median chars |", "|---|---|---|---|---|---|"]
    for k in sorted(g, key=str):
        v = g[k]
        ch = sorted(x["chars"] for x in v)[len(v) // 2]
        lines.append(f"| {k} | {len(v)} | {sum(x['answered'] for x in v)} | {sum(x['hit'] for x in v)} ({100 * sum(x['hit'] for x in v) // len(v)}%) | {sum(x.get('listed', x['hit']) for x in v)} | {ch} |")
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
