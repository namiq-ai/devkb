#!/usr/bin/env python3
"""Run the workflow benchmark (ODSF-310): whole developer tasks, three arms, interleaved.

  plain     Read, Grep, Glob, read-only git, and a neutral work-efficiently note (control.md)
  core      the same plus the devkb-sdlc MCP server with the 11 single-question tools and the devkb-sdlc skill
  workflow  the same plus the workflow toolset (one tool per developer task) and the task's own skill

Both graph arms are told to use the graph first: ODSF-308 showed that whether the model picks the graph up on its
own is a separate question (adoption), and this one asks what each tool surface costs when it is used.

  BENCH_CHECKOUT=... BENCH_GRAPH=... python3 devkb/bench/workflow_run.py TASKS.json OUT.jsonl --reps 4

Report: python3 devkb/bench/workflow_report.py OUT.jsonl. Write-up: docs/workflow-benchmark-odsf310.md.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_ROOT = Path(os.environ.get("BENCH_TOOL_ROOT", str(HERE.parent.parent)))  # checkout holding devkb/mcp_server.py
# Absolute: the MCP server starts inside the checkout, so a relative graph path would point nowhere and the tool arms
# would run with no tools while still told to use them (the 2026-11-15 addendum's first attempt).
CHECKOUT = str(Path(os.environ["BENCH_CHECKOUT"]).resolve()) if os.environ.get("BENCH_CHECKOUT") else ""  # pinned worktree
SNAPSHOT = str(Path(os.environ["BENCH_GRAPH"]).resolve()) if os.environ.get("BENCH_GRAPH") else ""  # graph at its HEAD
MODEL = os.environ.get("BENCH_MODEL", "sonnet")
PROJECT = os.environ.get("BENCH_PROJECT", "ODSF")
sys.path.insert(0, str(HERE))
import run as base  # noqa: E402  parse, norm, f1 and READ_TOOLS are shared with the lifecycle benchmark

ARMS = tuple(os.environ.get("BENCH_ARMS", "plain,core,workflow").split(","))  # ODSF-313 adds lean and pack
FORCE = " Use the devkb-sdlc tools first (load them with ToolSearch if they are not yet loaded), then read only what they name."


def skill(name: str) -> str:
    return (TOOL_ROOT / "skills" / name / "SKILL.md").read_text().split("---", 2)[2].strip()


LIMIT_TEXT = ("hit your", "usage limit", "rate limit")


def run_one(task: dict, arm: str, cfg_dir: Path) -> dict:
    """One run. A run the account's usage limit stopped is not a result: wait and run it again (deviation D3). A task
    the agent failed is never retried."""
    for attempt in range(48):
        res = _run_once(task, arm, cfg_dir)
        text = (res.get("answer") or "").lower()
        if not (res.get("is_error") and any(s in text for s in LIMIT_TEXT)):
            res["limit_retries"] = attempt
            return res
        print(f"usage limit on {task['id']} {arm}; waiting 10 minutes (attempt {attempt + 1})", flush=True)
        time.sleep(600)
    return res


def _run_once(task: dict, arm: str, cfg_dir: Path) -> dict:
    cfg = {"mcpServers": {}}
    if arm not in ("plain", "pack"):  # a pack arm loads no graph tools: the graph's answer is already in the prompt
        cfg["mcpServers"]["devkb-sdlc"] = {
            # --no-config: uv starts inside the checkout, and a repository's own uv settings (Prefect pins
            # `required-version`) must not stop the graph server; on 2026-11-15 they silently left Prefect's tool arms
            # without tools in all 90 runs.
            "command": "uv", "args": ["run", "--no-config", "--python", ">=3.10", "--no-project", "--with", "mcp>=1.23,<2", "python",
                                      str(TOOL_ROOT / "devkb" / "mcp_server.py"), "--project", PROJECT],
            "env": {"DEVKB_DIR": SNAPSHOT, "DEVKB_REPO": CHECKOUT, "DEVKB_TOOLSET": arm,
                    **({"DEVKB_EXTERNAL": "1"} if os.environ.get("DEVKB_EXTERNAL") == "1" else {}),
                    **({"DEVKB_NO_COVERAGE": "1"} if os.environ.get("DEVKB_NO_COVERAGE") == "1" else {})}}
    path = cfg_dir / f"mcp-{arm}-{threading.get_ident()}.json"
    path.write_text(json.dumps(cfg))
    control = (TOOL_ROOT / "devkb" / "bench" / "control.md").read_text()
    addendum = {"plain": control, "pack": control, "core": skill("devkb-sdlc"), "lean": skill("devkb-lean"),
                "lean-pack": skill("devkb-lean-pack"),
                "workflow": skill(task["skill"])}[arm]
    tools = base.READ_TOOLS + (["mcp__devkb-sdlc"] if arm not in ("plain", "pack") else [])
    prompt = task["prompt"] + (FORCE if arm not in ("plain", "pack") else "")
    if arm == "pack":
        prompt += "\n\n" + task["pack"]
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json",
           "--verbose", "--max-turns", os.environ.get("BENCH_MAX_TURNS", "30"), "--no-session-persistence", "--mcp-config", str(path), "--strict-mcp-config",
           "--append-system-prompt", addendum, "--allowedTools", *tools]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=CHECKOUT, capture_output=True, text=True, timeout=900)
        stdout = proc.stdout
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
    calls, graph, rbytes, used = 0, 0, 0, []
    final: dict = {}
    mcp_ok = arm in ("plain", "pack")  # a tool arm counts only when its graph server connected
    contexts: dict[str, int] = {}  # message id -> tokens of context that message was given (insertion-ordered)
    for line in stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            mcp_ok = mcp_ok or any(m.get("name") == "devkb-sdlc" and m.get("status") == "connected"
                                   for m in e.get("mcp_servers") or [])
        elif e.get("type") == "assistant":
            mu = e["message"].get("usage") or {}
            if e["message"].get("id") and mu:
                contexts[e["message"]["id"]] = (mu.get("input_tokens", 0) + mu.get("cache_creation_input_tokens", 0)
                                                + mu.get("cache_read_input_tokens", 0))
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    calls += 1
                    if c["name"].startswith("mcp__devkb-sdlc"):
                        graph += 1
                        used.append(c["name"].split("__")[-1])
        elif e.get("type") == "user" and isinstance(e["message"].get("content"), list):
            rbytes += sum(len(json.dumps(c.get("content"))) for c in e["message"]["content"] if c.get("type") == "tool_result")
        elif e.get("type") == "result":
            final = e
    u = final.get("usage", {})
    cw = u.get("cache_creation") or {}
    ctx = list(contexts.values())
    return {"cost": final.get("total_cost_usd"), "turns": final.get("num_turns"), "secs": round(time.time() - t0, 1),
            "fresh": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("output_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0),
            # token kinds: uncached input, cache writes (by lifetime), thinking; context size per model call
            "input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
            "cache_write_5m": cw.get("ephemeral_5m_input_tokens", 0), "cache_write_1h": cw.get("ephemeral_1h_input_tokens", 0),
            "thinking": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0), "model_calls": len(ctx),
            "ctx_initial": ctx[0] if ctx else 0, "ctx_peak": max(ctx) if ctx else 0, "ctx_final": ctx[-1] if ctx else 0,
            "tool_calls": calls,
            "graph_calls": graph, "graph_tools": used, "result_bytes": rbytes,
            "mcp_connected": mcp_ok,
            "is_error": bool(final.get("is_error")) or not final or not mcp_ok, "answer": final.get("result", "")}


def score(task: dict, answer: str) -> dict:
    a, t, f1, norm = base.parse(answer), task["truth"], base.f1, base.norm
    if task["kind"] == "rca":
        parts = {"raiser": 1.0 if norm(a.get("raiser", "")) == norm(t["raiser"]) else 0.0,
                 "callers": f1(a.get("callers"), t["callers"]), "tests": f1(a.get("test_files"), t["test_files"])}
    elif task["kind"] == "err_to_handler":
        parts = {"raiser": 1.0 if norm(a.get("raiser", "")) == norm(t["raiser"]) else 0.0,
                 "handlers": f1(a.get("handlers"), t["handlers"]), "tests": f1(a.get("test_files"), t["test_files"])}
    elif task["kind"] == "impact":
        parts = {"handlers": f1(a.get("handlers"), t["handlers"]), "tests": f1(a.get("test_files"), t["test_files"])}
    elif task["kind"] == "ticket_code":  # ADDENDUM-1 S2
        parts = {"functions": f1(a.get("functions"), t["functions"]), "tests": f1(a.get("test_files"), t["test_files"])}
    elif task["kind"] == "commit_trace":
        parts = {k: 1.0 if str(a.get(k, "")).strip().upper() == str(t[k]).upper() else 0.0 for k in ("ticket", "epic", "spec")}
    elif task["kind"] == "refactor":
        parts = {"files": f1(a.get("caller_files"), t["caller_files"]), "tests": f1(a.get("test_files"), t["test_files"])}
        if "blocked_files" in t:  # ODSF-315: a repository with no role profiles asks no boundary question
            parts["blocked"] = f1(a.get("blocked_files"), t["blocked_files"])
    else:  # onboard: how many of the three named are in the true top five (ties at fifth place kept)
        got = [norm(x) for x in (a.get("top") or [])][:3]
        parts = {"p_at_3": sum(1 for g in got if g in {norm(x) for x in t["top5"]}) / 3}
    return {"score": round(sum(parts.values()) / len(parts), 3), "parts": {k: round(v, 3) for k, v in parts.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("out")
    ap.add_argument("--reps", type=int, default=4)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--seed", type=int, default=310)
    ns = ap.parse_args()
    if not (CHECKOUT and SNAPSHOT):
        ap.error("set BENCH_CHECKOUT (pinned worktree) and BENCH_GRAPH (graph snapshot directory)")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CHECKOUT, capture_output=True, text=True).stdout.strip()
    built = json.loads((Path(SNAPSHOT) / "manifest.json").read_text()).get("git_head", "")
    if head != built:
        sys.exit(f"graph snapshot {built[:8]} is not the checkout {head[:8]}: the comparison would not be fair")
    tasks = json.load(open(ns.tasks))
    rnd = random.Random(ns.seed)
    cfg_dir = Path(ns.out).resolve().parent
    jobs = [(t, rep, arm) for t in tasks for rep in range(ns.reps) for arm in ARMS]
    rnd.shuffle(jobs)
    for arm in ARMS:  # one discarded warm-up per arm, so no arm alone pays the cold prompt cache
        run_one(tasks[0], arm, cfg_dir)
    lock = threading.Lock()

    def job(j):
        t, rep, arm = j
        res = run_one(t, arm, cfg_dir)
        valid = not res["is_error"] and bool(base.parse(res["answer"]))
        row = {"task": t["id"], "kind": t["kind"], "arm": arm, "rep": rep, "valid": valid, "model": MODEL, "project": PROJECT,
               **{k: v for k, v in res.items() if k != "answer"},
               **(score(t, res["answer"]) if valid else {"score": 0.0, "parts": {}}),
               # the whole answer (capped far above any real one), so a run can be rescored when a truth is corrected;
               # 1,500 characters cut most long file lists in two (lnbits get_wallet, 2026-11-15)
               "answer": res["answer"][:50000]}
        with lock, open(ns.out, "a") as out:
            out.write(json.dumps(row) + "\n")
        print(t["id"], arm, rep, "valid" if valid else "INVALID", row["score"], row["cost"], row["turns"], row["graph_calls"], flush=True)

    with ThreadPoolExecutor(ns.workers) as pool:
        list(pool.map(job, jobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
