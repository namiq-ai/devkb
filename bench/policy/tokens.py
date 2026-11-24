"""Per-run token structure from the stream: per model call (assistant message id) its usage."""
import json, sys, re
from pathlib import Path
from collections import Counter, defaultdict
S = Path(__file__).resolve().parent
sys.path.insert(0, str(S.parent / "audit"))
from toolmix import classify, size

def analyse(run):
    calls = {}            # message id -> usage (last seen wins: streaming repeats the id)
    order = []
    kinds, rchars = {}, Counter()
    res = {}
    init_tools = 0; mcp_tools = 0
    for line in open(S/"runs"/run/"stream.jsonl"):
        try: e = json.loads(line)
        except ValueError: continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            init_tools = len(e.get("tools", [])); mcp_tools = sum(1 for t in e.get("tools", []) if t.startswith("mcp__"))
        if e.get("type") == "result": res = e
        m = e.get("message")
        if not isinstance(m, dict): continue
        if e.get("type") == "assistant" and m.get("id"):
            if m["id"] not in calls: order.append(m["id"])
            calls[m["id"]] = m.get("usage") or {}
            for x in m.get("content") or []:
                if isinstance(x, dict) and x.get("type") == "tool_use":
                    kinds[x["id"]] = "devkb" if x["name"].startswith("mcp__devkb") else classify(x["name"], x.get("input", {}))
        for x in m.get("content") or []:
            if isinstance(x, dict) and x.get("type") == "tool_result" and x.get("tool_use_id") in kinds:
                rchars[kinds[x["tool_use_id"]]] += size(x.get("content", ""))
    us = [calls[i] for i in order]
    ctx = [u.get("input_tokens",0)+u.get("cache_read_input_tokens",0)+u.get("cache_creation_input_tokens",0) for u in us]
    mu = res.get("modelUsage") or {}
    return {"run": run, "calls": len(us), "base_ctx": ctx[0] if ctx else 0, "final_ctx": ctx[-1] if ctx else 0,
            "sum_ctx": sum(ctx), "cache_read": sum(u.get("cache_read_input_tokens",0) for u in us),
            "cache_write": sum(u.get("cache_creation_input_tokens",0) for u in us), "fresh_in": sum(u.get("input_tokens",0) for u in us),
            "out": sum(u.get("output_tokens",0) for u in us), "cost": res.get("total_cost_usd",0),
            "cost_by_model": {k: round(v.get("costUSD",0),3) for k,v in mu.items()}, "tools": init_tools, "mcp_tools": mcp_tools,
            "result_chars": dict(rchars)}
if __name__ == "__main__":
    rows = [analyse(d.name) for d in sorted((S/"runs").iterdir()) if d.name.startswith("p") and (d/"end").exists()]
    json.dump(rows, open(S/"tokens-policy.json","w"), indent=1)
    k = lambda n: f"{n/1000:.0f}k"
    print("| Run | Model calls | Tools offered (MCP) | Base ctx/call | Final ctx | Σ ctx | cache read | cache write | out | tool-result chars (search/read/run/devkb) | Cost | by model |")
    for r in rows:
        rc = r["result_chars"]
        print(f"| {r['run']} | {r['calls']} | {r['tools']} ({r['mcp_tools']}) | {k(r['base_ctx'])} | {k(r['final_ctx'])} | {k(r['sum_ctx'])} | {k(r['cache_read'])} | {k(r['cache_write'])} | {k(r['out'])} | {k(rc.get('search',0))}/{k(rc.get('read',0))}/{k(rc.get('run',0))}/{k(rc.get('devkb',0))} | ${r['cost']:.2f} | {r['cost_by_model']} |")
