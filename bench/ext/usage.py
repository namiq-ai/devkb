#!/usr/bin/env python3
"""How an agent used devkb in the external C++ benchmark: whether, when, with what, and whether the answer was the one the fix needed.

For every run (a directory under RUNS with a stream.jsonl) of the given arms, and for each devkb navigation command (`devkb symbol|outline|uses|pack|docs`) in it:
  position   which tool call it was (1 = the agent's first action, before any hook had spoken)
  command    subcommand and query
  answered   the output was not empty and not "no match"
  fixfile    the output names a source file the real fix commit changed (the proxy for "the answer pointed at the right place")
  next       the tool the agent used right after
and per run: used, first-call use, calls, calls that were followed by grep / sed / cat on the same file.

  usage.py [--arms a,b] [--runs DIR] [--results FILE]      prints a table per ticket and a summary; --json prints the rows"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXT = Path.home() / ".cache" / "devkb" / "ext"
NAV = re.compile(r"(?:^|[;&|(]\s*|\s)devkb\s+(symbol|outline|uses|pack|docs|callers|impact)\b([^;&|\n]*)")


def tickets() -> dict[str, dict]:
    return {t["id"]: t for t in json.loads((HERE / "tickets-yaml-cpp.json").read_text())}


def fix_files(repo: Path, sha: str) -> set[str]:
    out = subprocess.run(["git", "-C", str(repo), "show", "--name-only", "--format=", sha], capture_output=True, text=True).stdout.split()
    return {f for f in out if f.startswith("src/") or f.startswith("include/")}


def stream(path: Path):
    calls, results = [], {}
    for line in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        for c in m["content"]:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                calls.append(c)
            elif c.get("type") == "tool_result":
                t = c.get("content")
                results[c.get("tool_use_id")] = t if isinstance(t, str) else " ".join(x.get("text", "") for x in t if isinstance(x, dict)) if isinstance(t, list) else ""
    return calls, results


def analyse(run: Path, files: set[str]) -> dict:
    calls, results = stream(run / "stream.jsonl")
    rows = []
    for i, c in enumerate(calls):
        cmd = str(c["input"].get("command") or "")
        for m in NAV.finditer(cmd) if c["name"] == "Bash" else []:
            out = results.get(c["id"], "")
            nxt = calls[i + 1] if i + 1 < len(calls) else None
            nxt_cmd = str((nxt or {}).get("input", {}).get("command") or (nxt or {}).get("input", {}).get("pattern") or "")
            rows.append({"pos": i + 1, "sub": m[1], "query": m[2].strip()[:60], "chars": len(out),
                         "answered": bool(out.strip()) and "no match" not in out.lower()[:300] and not out.lower().startswith("error"),
                         "fixfile": any(f in out for f in files),
                         "next": (nxt["name"] + (":" + re.split(r"[\s;|]", nxt_cmd.strip())[0] if nxt["name"] == "Bash" else "")) if nxt else "-",
                         "also_grep_same_call": bool(re.search(r"\b(grep|rg|sed|cat)\b", cmd[m.end():]))})
            break
    return {"run": run.name, "tool_calls": len(calls), "nav": rows}


def main(a: list[str]) -> int:
    runs_dir = Path(a[a.index("--runs") + 1]) if "--runs" in a else EXT / "runs"
    arms = set(a[a.index("--arms") + 1].split(",")) if "--arms" in a else None
    repo = EXT / "yaml-cpp"
    tk = tickets()
    ff = {tid: fix_files(repo, t["fix"]) for tid, t in tk.items()}
    res = []
    for d in sorted(runs_dir.glob("y*-*-r*")):
        tid, arm = d.name.split("-")[:2]
        if (arms and arm not in arms) or not (d / "stream.jsonl").exists() or tid not in ff:
            continue
        r = analyse(d, ff[tid])
        r.update(ticket=tid, arm=arm)
        res.append(r)
    if "--json" in a:
        print(json.dumps(res))
        return 0
    print("| ticket | runs | used devkb | as first action | nav calls | answered | named the fix file | followed by a search in the same command | next call |\n|---|---|---|---|---|---|---|---|---|")
    by = defaultdict(list)
    for r in res:
        by[r["ticket"]].append(r)
    tot = defaultdict(int)
    nxt_all = Counter()
    for tid in sorted(by):
        R = by[tid]
        nav = [n for r in R for n in r["nav"]]
        used, first = sum(1 for r in R if r["nav"]), sum(1 for r in R if any(n["pos"] == 1 for n in r["nav"]))
        row = (len(R), used, first, len(nav), sum(n["answered"] for n in nav), sum(n["fixfile"] for n in nav), sum(n["also_grep_same_call"] for n in nav))
        for k, v in zip(("runs", "used", "first", "nav", "ans", "fix", "chain"), row):
            tot[k] += v
        nxt = Counter(n["next"] for n in nav)
        nxt_all.update(nxt)
        print(f"| {tid} | {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {', '.join(f'{k} {v}' for k, v in nxt.most_common(3)) or '-'} |")
    print(f"| **all** | {tot['runs']} | {tot['used']} ({100 * tot['used'] // max(1, tot['runs'])}%) | {tot['first']} | {tot['nav']} | {tot['ans']} | {tot['fix']} | {tot['chain']} | {', '.join(f'{k} {v}' for k, v in nxt_all.most_common(4))} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
