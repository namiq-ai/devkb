import json, subprocess, collections, re, os
out = json.load(open("audit/replay_out.json"))
print(len(out))
c = collections.Counter()
for x in out:
    ctx = x["ctx"] or ""
    kind = "deny:" + ctx.split("\n")[0][:40] if x["dec"] else ("remind" if ctx.startswith("devkb guardrail") else "along:" + ctx.split("\n")[0][:30])
    c[kind] += 1
print(c)
sel = [x for x in out if not (x["ctx"] or "").startswith("devkb guardrail")]
print(len(sel))
for x in sel:
    cmd = x["in"].get("command") or json.dumps(x["in"])
    ctx = x["ctx"]
    print("#", x["i"], x["dec"], "|", cmd[:300].replace("\n", " ⏎ "))
    print("   ", len(ctx), "chars |", ctx.replace("\n", " ⏎ ")[:330])
