#!/usr/bin/env python3
"""The release performance check in one command (#224): OLD against NEW, with a noise pass.

  perf_release.py OLD_REF NEW_REF NAME=PATH [NAME=PATH ...] [--work DIR] [--max-load 2.0] [--reps 3] [--queries 5]

Unpacks both refs with `git archive`, then runs `bench/perf.py` three times, one pass after another: NEW, OLD, NEW again.
Before each pass it records the 1-minute load average and waits (up to --wait seconds) until it is under --max-load;
a pass that starts above it is flagged. It refuses a work directory on a memory-backed filesystem (tmpfs). It writes
`compare.md`: build time, peak memory, graph size and query medians per repository, each change marked `within noise`
when it is no larger than the difference between the two NEW passes.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def fs_type(path: Path) -> str:
    out = subprocess.run(["stat", "-f", "-c", "%T", str(path)], capture_output=True, text=True)
    return out.stdout.strip()


def refuse_tmpfs(path: Path) -> None:
    if fs_type(path) in ("tmpfs", "ramfs"):
        raise SystemExit(f"{path} is on a memory-backed filesystem ({fs_type(path)}): graphs and clones can fill it; "
                         "pass --work on a disk")


def load1() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


def wait_quiet(max_load: float, wait: int) -> tuple[float, bool]:
    t0 = time.time()
    while load1() > max_load and time.time() - t0 < wait:
        time.sleep(15)
    return load1(), load1() <= max_load


def unpack(ref: str, work: Path) -> Path:
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{ref}^{{commit}}"], capture_output=True, text=True, check=True).stdout.strip()
    d = work / f"code-{ref.replace('/', '_')}-{sha[:10]}"
    if not d.exists():
        d.mkdir(parents=True)
        tar = subprocess.run(["git", "-C", str(REPO), "archive", sha], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(d)], input=tar, check=True)
    return d


def medians(res: dict) -> dict:
    out = {}
    for name, r in res["repos"].items():
        out[name] = {"build s": st.median(b["secs"] for b in r["build"]), "peak MB": max(b["peak_mb"] for b in r["build"]),
                     "graph MB": r["graph_mb"], **{f"{q} s": v["median_s"] for q, v in r["queries"].items()}}
    return out


def compare(old: dict, new_a: dict, new_b: dict) -> str:
    """One table per repository. A change is within noise when |NEW - OLD| <= |NEW_a - NEW_b| (NEW = mean of the two)."""
    o, a, b = medians(old), medians(new_a), medians(new_b)
    lines = []
    for name in a:
        lines += [f"### {name}", "", "| Metric | OLD | NEW (two passes) | Change | |", "|---|---|---|---|---|"]
        for k in a[name]:
            if k not in o.get(name, {}) or k not in b.get(name, {}):
                continue
            new = (a[name][k] + b[name][k]) / 2
            noise = abs(a[name][k] - b[name][k])
            old_v = o[name][k]
            ch = 100 * (new / old_v - 1) if old_v else 0.0
            mark = "within noise" if abs(new - old_v) <= noise else ""
            lines.append(f"| {k} | {old_v:g} | {a[name][k]:g} / {b[name][k]:g} | {ch:+.0f}% | {mark} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old"); ap.add_argument("new"); ap.add_argument("repos", nargs="+")
    ap.add_argument("--work", default=str(Path.home() / ".cache" / "devkb" / "perf-release"))
    ap.add_argument("--max-load", type=float, default=2.0); ap.add_argument("--wait", type=int, default=600)
    ap.add_argument("--reps", type=int, default=3); ap.add_argument("--queries", type=int, default=5)
    a = ap.parse_args(argv)
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    refuse_tmpfs(work)
    out = work / f"{a.old.replace('/', '_')}-vs-{a.new.replace('/', '_')}"
    out.mkdir(exist_ok=True)
    code = {"old": unpack(a.old, work), "new": unpack(a.new, work)}
    passes = [("new-a", "new"), ("old", "old"), ("new-b", "new")]
    log = {}
    targets = out / "targets.json"
    for label, which in passes:
        load, quiet = wait_quiet(a.max_load, a.wait)
        log[label] = {"code": str(code[which]), "load_1min": load, "quiet": quiet}
        print(f"=== {label} ({which}) load {load:.2f}{'' if quiet else ' ABOVE --max-load: flagged'}", flush=True)
        subprocess.run([sys.executable, str(code["new"] / "bench" / "perf.py"), str(code[which]), label, str(out / f"{label}.json"),
                        *a.repos, "--reps", str(a.reps), "--queries", str(a.queries), "--targets", str(targets)], check=True)
    (out / "passes.json").write_text(json.dumps(log, indent=1) + "\n")
    res = {k: json.loads((out / f"{k}.json").read_text()) for k, _ in passes}
    head = [f"# Performance: {a.old} against {a.new}", "", "| Pass | Code | Load before | |", "|---|---|---|---|"]
    head += [f"| {k} | {Path(v['code']).name} | {v['load_1min']:.2f} | {'' if v['quiet'] else 'flagged: above --max-load'} |" for k, v in log.items()]
    (out / "compare.md").write_text("\n".join(head) + "\n\n" + compare(res["old"], res["new-a"], res["new-b"]) + "\n")
    print(out / "compare.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
