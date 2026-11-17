"""Tool mix of agent transcripts: how much of an audit went through devkb versus grep/read.

  python toolmix.py LABEL=TRANSCRIPT.jsonl [...]

Per transcript: tool calls by class and the characters each class returned to the model, plus the share of the
first navigation step that was devkb. Classes: devkb (devkb CLI), search (grep/rg/git grep/Grep/Glob/find/ls),
read (Read, cat/sed/head/tail/awk on files, git show/blame/diff/log), run (python repro scripts, pytest, make),
other.
"""
import json
import re
import sys
from collections import Counter

DEVKB = re.compile(r"(devkb\.cli|(^|[\s;&|/])devkb)\s+(symbol|outline|uses|docs|pack|query|coverage|audit)\b")
VAR = re.compile(r"\$\{?\w+\}?\s+(symbol|outline|uses|docs|pack|query|coverage|audit)\b")   # P="... devkb.cli"; $P uses X


def devkb_queries(c):
    n = len(DEVKB.findall(c))
    if "devkb.cli" in c or re.search(r"=\S*devkb[\"' ]", c):
        n += len(VAR.findall(c))
    return n
SEARCH = re.compile(r"(^|[\s;&|(])(grep|rg|git grep|find|ls)\b")
READ = re.compile(r"(^|[\s;&|(])(cat|sed|head|tail|awk|nl|wc|git (show|blame|diff|log))\b")
RUN = re.compile(r"(python3?|\.venv/bin/python|pytest|make)\b")


def classify(name, inp):
    if name == "Bash":
        c = inp.get("command", "")
        if "<<" in c and re.search(r"cat\s*>", c):
            return "run"                    # writing a repro script
        if devkb_queries(c):
            return "devkb"
        if RUN.search(c) and not READ.search(c.split("|")[0]) and not SEARCH.search(c.split("|")[0]):
            return "run"
        if SEARCH.search(c):
            return "search"
        if READ.search(c):
            return "read"
        return "other"
    if name in ("Grep", "Glob"):
        return "search"
    if name == "Read":
        return "read"
    return "other"


def size(content):
    if isinstance(content, str):
        return len(content)
    return sum(len(x.get("text", "")) for x in content if isinstance(x, dict))


def main():
    rows = []
    for arg in sys.argv[1:]:
        label, path = arg.split("=", 1)
        calls, chars, kinds = Counter(), Counter(), {}
        order = []
        for line in open(path):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            msg = e.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for x in content:
                if x.get("type") == "tool_use":
                    k = classify(x["name"], x.get("input", {}))
                    kinds[x["id"]] = k
                    calls[k] += 1
                    order.append(k)
                    if k == "devkb":
                        calls["devkb queries"] += devkb_queries(x.get("input", {}).get("command", ""))
                elif x.get("type") == "tool_result" and x.get("tool_use_id") in kinds:
                    chars[kinds[x["tool_use_id"]]] += size(x.get("content", ""))
        nav = [k for k in order if k in ("devkb", "search", "read")]
        rows.append((label, calls, chars, nav))
    classes = ["devkb", "search", "read", "run", "other"]
    print("| transcript | devkb queries | " + " | ".join(f"{c} calls (k chars)" for c in classes) + " | devkb share of navigation calls | devkb share of navigation text |")
    print("|---|---|" + "---|" * (len(classes) + 2))
    for label, calls, chars, nav in rows:
        navc = sum(calls[c] for c in ("devkb", "search", "read"))
        navt = sum(chars[c] for c in ("devkb", "search", "read"))
        print(f"| {label} | {calls['devkb queries']} | " + " | ".join(f"{calls[c]} ({chars[c] / 1000:.1f})" for c in classes)
              + f" | {calls['devkb'] / navc:.0%} | {chars['devkb'] / navt:.0%} |" if navc and navt else "")


if __name__ == "__main__":
    main()
