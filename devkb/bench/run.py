#!/usr/bin/env python3
"""Run the lifecycle benchmark: each task asked with and without the process graph (ODSF-308).

  python3 run.py TASKS.json OUT.jsonl --reps 5 [--only S1,S3] [--seed 7]

Arms: `plain` has Read, Grep, Glob and read-only git; `graph` has the same plus the devkb-sdlc
MCP server over a pinned graph snapshot and the skill, used if the model chooses; `graph_forced` adds an
instruction to use the graph first, to show what the graph can do when it is actually used. Both get a system-prompt addendum of similar length
(the skill for graph, a neutral work-efficiently note for plain), so prompt length is not the
difference. Runs are interleaved in random order with a discarded warm-up per arm.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKOUT = os.environ.get("BENCH_CHECKOUT", "")  # pinned worktree the agents work in
TOOL_ROOT = os.environ.get("BENCH_TOOL_ROOT", str(HERE.parent.parent))  # checkout holding devkb/mcp_server.py
SNAPSHOT = os.environ.get("BENCH_GRAPH", "")     # pinned graph snapshot directory
MODEL = os.environ.get("BENCH_MODEL", "sonnet")
READ_TOOLS = ["Read", "Grep", "Glob", "Bash(git log:*)", "Bash(git show:*)", "Bash(git ls-files:*)", "Bash(git grep:*)",
              "Bash(git diff-tree:*)", "Bash(git diff:*)"]


def skill_body() -> str:
    """The skill's text without its frontmatter: what a loaded skill adds to the model's context."""
    return (Path(TOOL_ROOT) / "skills" / "devkb-sdlc" / "SKILL.md").read_text().split("---", 2)[2].strip()


def mcp_config(arm: str, path: Path) -> Path:
    cfg = {"mcpServers": {}}
    if arm in ("graph", "graph_forced"):
        cfg["mcpServers"]["devkb-sdlc"] = {
            "command": "uv", "args": ["run", "--python", ">=3.10", "--no-project", "--with", "mcp>=1.23,<2", "python",
                                      f"{TOOL_ROOT}/devkb/mcp_server.py", "--project", "ODSF"],
            "env": {"DEVKB_DIR": SNAPSHOT}}
    path.write_text(json.dumps(cfg))
    return path


def run_one(task: dict, arm: str, cfg_dir: Path, tools_extra: list[str] | None = None, cwd: str | None = None, max_turns: int = 30) -> dict:
    cfg = mcp_config(arm, cfg_dir / f"mcp-{arm}.json")
    addendum = (HERE / "control.md").read_text() if arm == "plain" else skill_body()
    tools = READ_TOOLS + (tools_extra or []) + (["mcp__devkb-sdlc"] if arm != "plain" else [])
    prompt = task["prompt"] + (" Use the devkb-sdlc tools first (load them with ToolSearch if they are not yet loaded), "
                               "then read only what they name." if arm == "graph_forced" else "")
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--verbose",
           "--max-turns", str(max_turns), "--no-session-persistence", "--mcp-config", str(cfg), "--strict-mcp-config",
           "--append-system-prompt", addendum, "--allowedTools", *tools]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd or CHECKOUT, capture_output=True, text=True, timeout=900)
    tool_calls = graph_calls = result_bytes = 0
    final: dict = {}
    for line in proc.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    tool_calls += 1
                    graph_calls += c["name"].startswith("mcp__devkb-sdlc")
        elif e.get("type") == "user" and isinstance(e["message"].get("content"), list):
            for c in e["message"]["content"]:
                if c.get("type") == "tool_result":
                    result_bytes += len(json.dumps(c.get("content")))
        elif e.get("type") == "result":
            final = e
    u = final.get("usage", {})
    return {"cost": final.get("total_cost_usd"), "turns": final.get("num_turns"), "secs": round(time.time() - t0, 1),
            "fresh": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("output_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0),
            "tool_calls": tool_calls, "graph_calls": graph_calls, "result_bytes": result_bytes,
            "is_error": bool(final.get("is_error")) or not final, "answer": final.get("result", "")}


# ── scoring ──────────────────────────────────────────────────────────────────
def norm(x: str) -> str:
    x = re.sub(r"^(?:\./|/)+", "", str(x).strip().strip("`"))   # a `./` prefix, not the characters (#86: `.github/`)
    if "::" in x:
        path, name = x.split("::", 1)
        return f"{path}::{name.split('.')[-1].split('(')[0].strip()}"
    return x


def f1(got, want) -> float:
    g, w = {norm(x) for x in (got or [])}, {norm(x) for x in (want or [])}
    if not g and not w:
        return 1.0
    hit = len(g & w)
    if not hit:
        return 0.0
    p, r = hit / len(g), hit / len(w)
    return 2 * p * r / (p + r)


def parse(text: str) -> dict:
    """The first JSON object in the answer. The model may add prose before or after it, and
    prose can contain braces, so try every opening brace rather than the span to the last one."""
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and obj:
            return obj
    return {}


def score(task: dict, answer: str) -> dict:
    a, t, kind = parse(answer), task["truth"], task["kind"]
    if kind == "callers":
        parts = {"callers": f1(a.get("callers"), t["callers"]), "test_files": f1(a.get("test_files"), t["test_files"]),
                 "owner": f1(a.get("owner"), t["owner"]), "forbidden": f1(a.get("forbidden_for"), t["forbidden_for"])}
    elif kind == "docs_recall":
        got = [norm(x) for x in (a.get("docs") or [])][:8]
        parts = {"recall": (len({*got} & {norm(x) for x in t["docs"]}) / len(t["docs"])) if t["docs"] else 1.0,
                 "exist": (sum(1 for g in got if (Path(CHECKOUT) / g).exists()) / len(got)) if got else 0.0}
    elif kind == "docs_set":
        parts = {"f1": f1(a.get("adrs"), t["adrs"])}
    elif kind == "set":
        parts = {"rules": 1.0 if sorted(a.get("failing_rules") or []) == sorted(t["failing_rules"]) else 0.0}
    elif kind == "review":
        parts = {"changed": f1(a.get("changed"), t["changed"]), "callers": f1(a.get("callers_outside"), t["callers_outside"]),
                 "tests": f1(a.get("test_files"), t["test_files"])}
    else:
        parts = {k: 1.0 if str(a.get(k)) == str(v) else 0.0 for k, v in t.items()}
    main = parts.get("recall", sum(parts.values()) / len(parts))
    return {"score": round(main, 3), "parts": {k: round(v, 3) for k, v in parts.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("out")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--only", default="")
    ap.add_argument("--seed", type=int, default=7)
    ns = ap.parse_args()
    if not (CHECKOUT and SNAPSHOT):
        ap.error("set BENCH_CHECKOUT (pinned worktree) and BENCH_GRAPH (graph snapshot directory)")
    tasks = [t for t in json.load(open(ns.tasks)) if not ns.only or t["stage"] in ns.only.split(",")]
    rnd = random.Random(ns.seed)
    cfg_dir = Path(ns.out).resolve().parent
    pairs = [(t, r) for t in tasks for r in range(ns.reps)]
    rnd.shuffle(pairs)
    with open(ns.out, "a") as out:
        for arm in ("plain", "graph", "graph_forced"):  # warm-up: one discarded run per arm so neither pays the cold cache alone
            run_one(tasks[0], arm, cfg_dir)
        for t, rep in pairs:
            for arm in rnd.sample(["plain", "graph", "graph_forced"], 3):
                res = run_one(t, arm, cfg_dir)
                valid = not res["is_error"] and bool(parse(res["answer"]))
                row = {"task": t["id"], "stage": t["stage"], "arm": arm, "rep": rep, "valid": valid,
                       **{k: v for k, v in res.items() if k != "answer"},
                       **(score(t, res["answer"]) if valid else {"score": 0.0, "parts": {}}), "answer": res["answer"][:1500]}
                out.write(json.dumps(row) + "\n")
                out.flush()
                print(t["id"], arm, rep, "valid" if valid else "INVALID", row["score"], row["cost"], row["turns"], row["graph_calls"], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
