#!/usr/bin/env python3
"""Run the Zephyr benchmark matrix (#447): tasks x arms x repetitions, a few runs at a time, resumable.

    batch.py plan  [--reps N]            the jobs and what is left to run, nothing started
    batch.py start [--reps N] [--jobs K] run what is left; refuses to start when a preflight check fails

Order is repetition-major (every task and arm once, then again), so an interrupted batch is balanced. A job whose record exists is skipped.
Each job is its own `zbench.py run` process in its own checkout and cache; nothing is shared between runs but the read-only templates.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zbench  # noqa: E402

TASKS = ["122187", "121844", "121059", "121873", "124453"]
ARMS = ["none", "cbm"]          # devkb stopped after its first runs (owner, 2026-11-24): its result is known; cbm stays to learn how it works


def jobs(reps: int) -> list[tuple[str, str, int]]:
    return [(pr, arm, r) for r in range(reps) for pr in TASKS for arm in ARMS]


def done(pr: str, arm: str, rep: int) -> bool:
    f = zbench.OUT / f"z{pr}-{arm}-r{rep}" / "record.json"
    try:
        r = json.loads(f.read_text())
        return "hidden" in r and not r["entry_problems"] and r["exit"] in (0, "0") and not r["metrics"]["is_error"]
    except (OSError, ValueError):
        return False


def preflight() -> list[str]:
    """What would make a batch worthless, checked before it starts (the 0.2.15 failures were all in the harness)."""
    bad = []
    shown = subprocess.run(["uv", "pip", "show", "--python", str(zbench.DEVKB_BIN / "python"), "devkb"], capture_output=True, text=True).stdout
    if "Version: 0.2.15" not in shown:
        bad.append("devkb in the arm's venv is not 0.2.15")
    if "mcp" not in subprocess.run(["uv", "pip", "list", "--python", str(zbench.DEVKB_BIN / "python")], capture_output=True, text=True).stdout.split():
        bad.append("the devkb venv lacks the mcp extra: its MCP server would not start")
    if subprocess.run([str(zbench.CBM), "--version"], capture_output=True, text=True).stdout.split()[-1:] != ["0.12.1"]:
        bad.append("codebase-memory-mcp is not 0.12.1")
    for pr in TASKS:
        g = zbench.RUN / "tmpl" / f"dkb-{pr}" / ".devkb"
        try:
            n = json.loads((g / "manifest.json").read_text())["node_count"]
            if n < 100000 or not (g / "nodes.jsonl").exists():
                bad.append(f"graph for {pr} looks incomplete ({n} nodes)")
        except (OSError, ValueError, KeyError):
            bad.append(f"graph for {pr} is not built (no manifest.json)")
        if not (zbench.RUN / "hidden" / pr).exists():
            bad.append(f"no hidden check for {pr}")
    for f in ("devkb_guardrail.py", "devkb_guardrail_post.py"):
        if not (zbench.GUARDRAIL / f).exists():
            bad.append(f"the 0.2.15 grep hook script {f} is missing")
    if not (zbench.CBM_TEMPLATE / ".claude" / "settings.json").exists():
        bad.append("the cbm Claude config template is missing")
    if shutil.disk_usage(str(zbench.WORK.parent)).free < 80 * 2**30:
        bad.append("less than 80 GB free")
    running = subprocess.run(["pgrep", "-f", "zbench.py run"], capture_output=True, text=True).stdout.split()
    if running:
        bad.append(f"another zbench run is active: {running}")
    try:
        rec = json.loads((zbench.OUT / "isolation" / "record.json").read_text())
        if not rec["passed"] or rec["claude"] != subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip():
            bad.append("the isolation self-test did not pass with this Claude Code version: run `zbench.py isolation`")
    except (OSError, ValueError, KeyError):
        bad.append("no isolation self-test record: run `zbench.py isolation`")
    for arm in zbench.ARMS:
        r = zbench.OUT / f"smoke-{arm}" / "record.json"
        try:
            rec = json.loads(r.read_text())
            if not all(rec["answer_ok"].values()) or rec["entry_problems"]:
                bad.append(f"smoke {arm} did not pass")
        except (OSError, ValueError, KeyError):
            bad.append(f"no smoke record for {arm}")
    return bad


def run_job(j: tuple[str, str, int]) -> str:
    pr, arm, rep = j
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "zbench.py"), "run", pr, arm, str(rep)], capture_output=True, text=True)
    return f"{pr} {arm} r{rep}: rc={r.returncode} {r.stdout.strip()[-200:]} {r.stderr.strip()[-200:] if r.returncode else ''}"


def main(a: list[str]) -> int:
    reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 7
    k = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 4
    todo = [j for j in jobs(reps) if not done(*j)]
    print(f"{len(jobs(reps))} jobs, {len(todo)} left; {len(TASKS)} tasks x {len(ARMS)} arms x {reps} reps, {k} at a time")
    if a[:1] == ["plan"]:
        return 0
    bad = preflight()
    if bad:
        print("PREFLIGHT FAILED:\n  " + "\n  ".join(bad))
        return 1
    with ThreadPoolExecutor(k) as pool:
        for line in pool.map(run_job, todo):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
