#!/usr/bin/env python3
"""The #447 structural probe with graph tools loaded upfront.

    upfront.py run VARIANT REP     one probe run; the record goes to $UPFRONT_ROOT/VARIANT/ (default ZBENCH_RUN/zbench-upfront)
    upfront.py task VARIANT PR REP one bug-fix run of a #447 task, scored by its hidden check
    upfront.py tasks               per task variant: entry check, hidden checks passed, ToolSearch calls, first-call context, cost
    upfront.py report              per variant: entry check (were the tools really loaded), graph calls, recall, turns, tokens, cost

The earlier probe listed the graph tools but Claude Code deferred all of them behind ToolSearch. A run here counts only if the session transcript
shows that none of the variant's upfront tools was deferred.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zbench  # noqa: E402

CBM = "mcp__codebase-memory-mcp__"
DKB = "mcp__devkb__"
VARIANTS = {
    # name: (harness arm, devkb toolset, MCP server loaded whole, tools removed, tools that must be upfront)
    "none": ("none", None, None, [], []),
    "devkb-default": ("devkb", "lean-pack", None, [], [DKB + n for n in ("symbol", "outline", "pack")]),
    "devkb-rel": ("devkb", "lean-pack", "devkb",
                  [DKB + n for n in ("rca_trace", "impact", "tests_for", "tests_to_run", "review_pack", "config", "search_docs")],
                  [DKB + n for n in ("symbol", "outline", "pack", "uses", "callers")]),
    "cbm-3": ("cbm", None, "codebase-memory-mcp",
              [CBM + n for n in ("check_index_coverage", "compare_graphs", "delete_project", "detect_changes", "get_architecture", "get_file_outline",
                                 "get_graph_schema", "index_repository", "index_status", "ingest_traces", "list_projects", "manage_adr", "query_graph",
                                 "search_code")],
              [CBM + n for n in ("search_graph", "trace_path", "get_code_snippet")]),
    # #448: the default toolset on the change's package, nothing removed, so `uses` loading with the prompt is the only difference
    "devkb-448": ("devkb", "lean-pack", None, [], [DKB + n for n in ("symbol", "outline", "pack", "uses")]),
}
ROOT = Path(os.environ.get("UPFRONT_ROOT") or zbench.RUN / "zbench-upfront")
PATCHED = {"devkb-448": zbench.RUN / "448" / "src"}          # a copy of the change's `devkb` package, put ahead of the 0.2.15 venv's


def configure(variant: str) -> str:
    arm, toolset, whole, removed, _ = VARIANTS[variant]
    zbench.OUT = ROOT / variant
    zbench.WORK = Path.home() / ".cache" / "devkb" / ROOT.name / variant
    zbench.DENY = zbench.DENY + removed
    sh, prepare = zbench.sh, zbench.prepare

    def sh_toolset(cmd, **kw):
        if toolset and "init" in cmd and "--toolset" in cmd:
            cmd = list(cmd)
            cmd[cmd.index("--toolset") + 1] = toolset
        return sh(cmd, **kw)

    def prepare_upfront(*a, **kw):
        w, info = prepare(*a, **kw)
        if whole:
            f = w / ".mcp.json"
            cfg = json.loads(f.read_text())
            cfg["mcpServers"][whole]["alwaysLoad"] = True
            f.write_text(json.dumps(cfg, indent=2))
        info["variant"] = variant
        info["mcp_json"] = (w / ".mcp.json").read_text() if (w / ".mcp.json").exists() else None
        return w, info

    env_for = zbench.env_for

    def env_patched(a, *args):
        env = env_for(a, *args)
        if variant in PATCHED and a == "devkb":
            env["PYTHONPATH"] = str(PATCHED[variant])
        return env

    zbench.sh, zbench.prepare, zbench.env_for = sh_toolset, prepare_upfront, env_patched
    return arm


def loading(stream: Path) -> dict:
    """From the session's own transcript: which MCP tools were deferred, and how often ToolSearch was called."""
    events = [json.loads(x) for x in stream.read_text().splitlines() if x.startswith("{")]
    init = next(e for e in events if e.get("type") == "system" and e.get("subtype") == "init")
    found = list((Path.home() / ".claude" / "projects").glob(f"*/{init['session_id']}.jsonl"))
    if not found:
        return {"transcript": False}
    deferred: set[str] = set()
    search = 0
    for line in found[0].read_text().splitlines():
        d = json.loads(line)
        a = d.get("attachment") or {}
        if a.get("type") == "deferred_tools_delta":
            deferred |= {n for n in a.get("addedNames", []) if n.startswith("mcp__")}
        if d.get("type") == "assistant":
            search += sum(1 for b in d["message"].get("content", []) if isinstance(b, dict) and b.get("name") == "ToolSearch")
    return {"transcript": True, "listed": sorted(n for n in init.get("tools", []) if n.startswith("mcp__")), "deferred": sorted(deferred),
            "tool_search_calls": search, "version": init.get("claude_code_version")}


def report() -> None:
    for variant, (_, _, _, _, upfront) in VARIANTS.items():
        rows = []
        for f in sorted((ROOT / variant).glob("probe-*/record.json")):
            r = json.loads(f.read_text())
            load = loading(f.parent / "stream.jsonl")
            ok = load["transcript"] and not (set(upfront) & set(load["deferred"])) and set(upfront) <= set(load["listed"]) and r["exit"] == 0
            rows.append((r, load, ok))
        if not rows:
            continue
        good = [r for r, _, ok in rows if ok]
        calls = {}
        for r in good:
            for k, v in r["metrics"]["calls_by_name"].items():
                calls[k] = calls.get(k, 0) + v
        med = lambda k: statistics.median([r["metrics"][k] for r in good]) if good else None  # noqa: E731
        print(json.dumps({"variant": variant, "runs": len(rows), "valid": len(good), "runs_using_graph": sum(r["metrics"]["graph_calls"] > 0 for r in good),
                          "graph_calls": sum(r["metrics"]["graph_calls"] for r in good), "recall_mean": round(statistics.mean([r["recall"] for r in good]), 3) if good else None,
                          "recall": [r["recall"] for r in good],
                          "per_question": [round(statistics.mean([r["scores"][i] for r in good]), 2) for i in range(6)] if good else None,
                          "turns_med": med("turns"), "tool_calls_med": med("tool_calls"), "tokens_med": med("tokens_total"), "cost_med": med("cost_usd"),
                          "cost_total": round(sum(r["metrics"]["cost_usd"] for r, _, _ in rows), 3), "api_ms_med": med("duration_api_ms"),
                          "calls_by_name": calls, "deferred": rows[0][1].get("deferred"), "tool_search_calls": sum(x.get("tool_search_calls", 0) for _, x, _ in rows),
                          "claude_code": sorted({x.get("version") for _, x, _ in rows})}))


def first_context(stream: Path) -> int:
    """Input tokens of the run's first model call: what the session loads before the agent has done anything."""
    for line in stream.read_text().splitlines():
        d = json.loads(line) if line.startswith("{") else {}
        if d.get("type") == "assistant":
            u = d["message"]["usage"]
            return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    return 0


def tasks() -> None:
    for variant, (_, _, _, _, upfront) in VARIANTS.items():
        rows = []
        for f in sorted((ROOT / variant).glob("z*/record.json")):
            r = json.loads(f.read_text())
            load = loading(f.parent / "stream.jsonl")
            ok = load["transcript"] and not (set(upfront) & set(load["deferred"])) and set(upfront) <= set(load["listed"]) and r["exit"] == 0
            rows.append((r, load, ok, first_context(f.parent / "stream.jsonl")))
        if not rows:
            continue
        good = [x for x in rows if x[2]]
        by = {}
        for r, load, _, ctx in good:
            t = by.setdefault(r["task"], {"n": 0, "pass": 0, "cost": 0.0, "turns": [], "graph": 0, "tool_search": 0})
            t["n"] += 1
            t["pass"] += bool(r["hidden"].get("passed"))
            t["cost"] = round(t["cost"] + r["metrics"]["cost_usd"], 4)
            t["turns"].append(r["metrics"]["turns"])
            t["graph"] += r["metrics"]["graph_calls"]
            t["tool_search"] += load["tool_search_calls"]
        calls = {}
        for r, *_ in good:
            for k, v in r["metrics"]["calls_by_name"].items():
                calls[k] = calls.get(k, 0) + v
        print(json.dumps({"variant": variant, "runs": len(rows), "valid": len(good), "passed": sum(t["pass"] for t in by.values()),
                          "cost_total": round(sum(t["cost"] for t in by.values()), 3), "tool_search_calls": sum(t["tool_search"] for t in by.values()),
                          "graph_calls": sum(t["graph"] for t in by.values()), "first_context_med": statistics.median([x[3] for x in good]) if good else None,
                          "tokens_med": statistics.median([r["metrics"]["tokens_total"] for r, *_ in good]) if good else None,
                          "calls_by_name": calls, "by_task": by, "invalid": [x[0]["tag"] for x in rows if not x[2]]}))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["run"] and len(a) == 3 and a[1] in VARIANTS:
        r = zbench.probe(configure(a[1]), int(a[2]))
        print(a[1], json.dumps({k: r[k] for k in ("tag", "exit", "seconds", "recall", "entry_problems")}, default=str), r["metrics"]["graph_calls"], "graph calls")
    elif a[:1] == ["task"] and len(a) == 4 and a[1] in VARIANTS:
        r = zbench.run(a[2], configure(a[1]), int(a[3]))
        print(a[1], json.dumps({k: r[k] for k in ("tag", "exit", "seconds", "entry_problems")}, default=str), r["hidden"].get("passed"), flush=True)
    elif a == ["report"]:
        report()
    elif a == ["tasks"]:
        tasks()
    else:
        print(__doc__)
        sys.exit(2)
