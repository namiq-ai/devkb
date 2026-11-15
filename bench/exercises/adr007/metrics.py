#!/usr/bin/env python3
"""Process metrics of one headless Claude Code run from its stream-json transcript.

  python3 metrics.py stream.jsonl ARM   ->  one JSON line: cost, turns, tokens by kind, context sizes, tool use,
                                           devkb use (MCP calls and `devkb pack/query/build` commands), bytes read
"""
import collections, json, re, sys

f, arm = sys.argv[1:3]
uses, tools, dk, builds, by, ctx, final = {}, collections.Counter(), [], [], collections.Counter(), {}, {}
for line in open(f):
    try:
        e = json.loads(line)
    except ValueError:
        continue
    if e.get("type") == "assistant":
        m = e["message"]; u = m.get("usage") or {}
        if m.get("id") and u:
            ctx[m["id"]] = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        for c in m.get("content", []):
            if c.get("type") == "tool_use":
                uses[c["id"]] = c; n = c["name"]
                tools["devkb-mcp" if n.startswith("mcp__devkb") else n] += 1
                cmd = c["input"].get("command", "") if n == "Bash" else ""
                if n.startswith("mcp__devkb"):
                    dk.append(n.split("__")[-1])
                else:
                    code = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n\1\b", " ", cmd, flags=re.S)  # heredoc bodies are data
                    code = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", code)  # so are quoted strings
                    for seg in re.split(r"&&|\|\||;|\||\n", code):
                        seg = re.sub(r"^\s*(export\s+)?(\w+=\S+\s+)*", "", seg)  # leading VAR=value assignments
                        m = re.match(r"(?:\S*/)?(?:devkb|python3?\s+-m\s+devkb\.cli)\s+(pack|query|build)\b", seg)
                        if m:  # pack/query is asking the graph; build is the agent testing its own extractor
                            (dk if m.group(1) != "build" else builds).append(m.group(1) + " " + seg.split(m.group(1), 1)[1].strip()[:60])
    if e.get("type") == "user" and isinstance(e["message"].get("content"), list):
        for c in e["message"]["content"]:
            if c.get("type") == "tool_result" and c.get("tool_use_id") in uses:
                u = uses[c["tool_use_id"]]; k = u["name"]
                if k == "Bash":
                    k = "read" if re.match(r"\s*(cat|sed|grep|head|tail|git ls|ls|wc)\b", u["input"].get("command", "")) else "run"
                elif k == "Read":
                    k = "read"
                elif k.startswith("mcp__devkb"):
                    k = "devkb"
                by[k] += len(json.dumps(c.get("content")))
    if e.get("type") == "result":
        final = e
u = final.get("usage", {}); v = list(ctx.values()); tot = sum(by.values()) or 1
print(json.dumps({"arm": arm, "cost_usd": round(final.get("total_cost_usd", 0), 3), "turns": final.get("num_turns"),
                  "wall_s": round(final.get("duration_ms", 0) / 1000), "model_calls": len(v),
                  "input": u.get("input_tokens"), "cache_write": u.get("cache_creation_input_tokens"),
                  "cache_read": u.get("cache_read_input_tokens"), "output": u.get("output_tokens"),
                  "ctx_initial": v[0] if v else 0, "ctx_peak": max(v) if v else 0, "tools": dict(tools.most_common()),
                  "devkb_uses": dk, "devkb_builds_run": len(builds), "tool_output_kB": {k: round(x / 1000) for k, x in by.most_common()},
                  "read_share": round(by["read"] / tot, 2)}))
