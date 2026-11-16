#!/usr/bin/env python3
"""Where does the money go in a short agent run? Per model call: the context it sent (cached prefix read or written, new input),
and the output. Splits each run's cost into: writing the prompt prefix to the cache (call 1), re-reading the prefix on every later
call, the growth of the conversation (tool results and the agent's own messages), and output.

  cost_breakdown.py RUN_DIR_GLOB ...      e.g. 'eval/hop/*.jsonl' 'eval/nav/*.jsonl'
Prices ($ per million tokens), fitted to the reported cost of 84 runs with zero error: input 2, cache write 4, cache read 0.10, output 10."""
import collections, glob, json, re, sys

P_IN, P_W5, P_W1, P_R, P_OUT = 2.0, 4.0, 4.0, 0.10, 10.0   # fitted on 84 runs against the reported cost: exact

def calls(path):
    last, order = {}, []
    for l in open(path):
        try: e = json.loads(l)
        except ValueError: continue
        if e.get("type") == "assistant" and e["message"].get("id"):
            mid = e["message"]["id"]
            if mid not in last: order.append(mid)
            last[mid] = e["message"].get("usage") or {}
    cost = 0.0; mu = {}
    for l in open(path):
        try: e = json.loads(l)
        except ValueError: continue
        if e.get("type") == "result":
            cost = max(cost, e.get("total_cost_usd", 0) or 0)
            for u in (e.get("modelUsage") or {}).values():
                for k, v in u.items():
                    if isinstance(v, (int, float)): mu[k] = max(mu.get(k, 0), v)
    return [last[m] for m in order], cost, mu

def breakdown(path):
    us, cost, mu = calls(path)
    if not us: return None
    cw1 = mu.get("cacheCreationEphemeral1hInputTokens", 0); cw_all = mu.get("cacheCreationInputTokens", 0)
    rows = []
    for n, u in enumerate(us):
        rows.append(dict(n=n, new=u.get("input_tokens", 0) or 0, cw=u.get("cache_creation_input_tokens", 0) or 0, cr=u.get("cache_read_input_tokens", 0) or 0, out=u.get("output_tokens", 0) or 0))
    ctx = [r["new"] + r["cw"] + r["cr"] for r in rows]
    return dict(rows=rows, ctx=ctx, cost=cost, mu=mu, w1_share=(cw1 / cw_all if cw_all else 0))

if __name__ == "__main__":
    groups = collections.defaultdict(list)
    for pat in sys.argv[1:]:
        for f in sorted(glob.glob(pat)):
            m = re.match(r".*/(plain|devkb)-", f)
            b = breakdown(f)
            if m and b: groups[m.group(1)].append(b)
    for arm, bs in groups.items():
        n = len(bs); mean = lambda xs: sum(xs) / len(xs)
        first = mean([b["ctx"][0] for b in bs]); last = mean([b["ctx"][-1] for b in bs]); k = mean([len(b["ctx"]) for b in bs])
        grow = mean([(b["ctx"][-1] - b["ctx"][0]) for b in bs])
        tot = collections.Counter()
        for b in bs:
            r = b["rows"]
            tot["cw_first"] += r[0]["cw"] * (P_W1 if b["w1_share"] > 0.5 else P_W5) / 1e6
            tot["cr_first"] += r[0]["cr"] * P_R / 1e6
            tot["new_first"] += r[0]["new"] * P_IN / 1e6
            for x in r[1:]:
                tot["cw_later"] += x["cw"] * (P_W1 if b["w1_share"] > 0.5 else P_W5) / 1e6
                tot["cr_later"] += x["cr"] * P_R / 1e6
                tot["new_later"] += x["new"] * P_IN / 1e6
            tot["out"] += sum(x["out"] for x in r) * P_OUT / 1e6
            tot["reported"] += b["cost"]
        s = {k: v / n for k, v in tot.items()}; modelled = sum(v for k, v in s.items() if k != "reported")
        print(f"{arm}: {n} runs, {k:.1f} model calls per run | context per call: first {first / 1000:.1f}k, last {last / 1000:.1f}k (growth over the run {grow / 1000:.1f}k)")
        print(f"   $ per run: reported {s['reported']:.4f}  modelled {modelled:.4f}")
        for name, key in (("call 1: prompt prefix written to cache", "cw_first"), ("call 1: prefix read from cache", "cr_first"), ("call 1: uncached input", "new_first"),
                          ("later calls: the prefix and history read from cache", "cr_later"), ("later calls: new content written to cache", "cw_later"),
                          ("later calls: uncached input", "new_later"), ("output tokens", "out")):
            print(f"      {name:56s} {s[key]:.4f}  {100 * s[key] / modelled:4.0f}%")
