#!/usr/bin/env python3
"""Per run: how many grep calls, file loads and devkb calls, and how much text each returned to the model.
  tool_usage.py STREAM.jsonl ...  (Claude Code stream-json transcripts)"""
import json, re, sys, collections

def classify(name, inp):
    if name.startswith("mcp__") and "devkb" in name: return "devkb"
    if name == "Grep": return "grep"
    if name == "Read": return "file load"
    if name == "Glob": return "find/list"
    if name == "Bash":
        cmd = (inp.get("command") or "").strip()
        first = re.split(r"\s*(?:&&|\|\||;|\|)\s*", cmd)[0]
        # a pipeline that greps counts as a grep, a cat/sed/head/tail of a file as a file load
        if re.search(r"\b(grep|rg|ag)\b", cmd): return "grep"
        if re.match(r"(cat|sed|head|tail|less|awk|nl)\b", first): return "file load"
        if re.match(r"(find|ls|tree|wc)\b", first): return "find/list"
        if re.search(r"(^|[\s;&|])devkb\s+(pack|query|build|mcp)\b", cmd): return "devkb"
        return "other shell"
    return "other"

def usage(path):
    calls, size, uses = collections.Counter(), collections.Counter(), {}
    for l in open(path):
        try: e = json.loads(l)
        except ValueError: continue
        if e.get("type") == "assistant":
            for x in e["message"]["content"]:
                if x.get("type") == "tool_use":
                    k = classify(x["name"], x["input"]); uses[x["id"]] = k; calls[k] += 1
        if e.get("type") == "user" and isinstance(e["message"].get("content"), list):
            for x in e["message"]["content"]:
                if x.get("type") == "tool_result" and x.get("tool_use_id") in uses:
                    c = x.get("content"); n = len(c if isinstance(c, str) else json.dumps(c))
                    size[uses[x["tool_use_id"]]] += n
    return calls, size

if __name__ == "__main__":
    for p in sys.argv[1:]:
        c, s = usage(p); print(p.split("/")[-1], dict(c), {k: round(v / 1000) for k, v in s.items()})
