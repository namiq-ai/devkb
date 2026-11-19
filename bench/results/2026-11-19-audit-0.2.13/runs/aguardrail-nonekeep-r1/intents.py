import json, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
repo = root / "audit" / "_rp"
sys.path.insert(0, str(repo)); sys.path.insert(0, str(repo / "scripts"))
import devkb_guardrail as g
for i, line in enumerate(open(root / "audit" / "searches.jsonl")):
    s = json.loads(line)
    tool, inp = s["tool"], s["input"]
    if tool == "Grep":
        pattern = inp.get("pattern", ""); paths, why = g.grep_tool_search(inp, repo)
    elif tool == "Bash":
        if not g.search_segments(inp.get("command", "")): continue
        pattern = g.bash_pattern(inp["command"]); paths, why = g.bash_search(inp["command"], repo)
        if not paths: continue
    else:
        continue
    r, _ = g.repo_of(paths)
    if r is None: continue
    intent = g.classify(tool, inp, pattern, why, paths)
    cmd = inp.get("command") or json.dumps(inp)
    print(f"{i}\t{intent}\t{why}\t{pattern[:40]!r}\t{cmd[:170]!r}")
