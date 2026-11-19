"""Label each answered search by the intent of the segment that triggered devkb's answer, and judge whether the answer matches."""
import json, re, collections, sys
rows = [json.loads(l) for l in open("replay-0212.jsonl")]
def answered_names(a):
    return re.findall(r"signature of `[^`]*?::([\w.]+)`", a) + re.findall(r"^`?([\w.]+)`? is defined", a, re.M) + re.findall(r"definition search from the graph[^`]*`([\w.]+)`", a)
def segs(cmd):
    cmd = re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", " <<HEREDOC ", cmd, flags=re.S)
    return [s.strip() for s in re.split(r"&&|\|\||;|\n", cmd) if s.strip()]
def intent(seg, tool_inp=None):
    if tool_inp is not None:                      # the Grep tool
        p = tool_inp.get("pattern", ""); ctx = tool_inp.get("-A") or tool_inp.get("-B") or tool_inp.get("-C") or tool_inp.get("context")
        mode = tool_inp.get("output_mode", "files_with_matches")
        if mode == "count": return "count"
        if re.search(r"\b(def|class|function|func|struct)\s", p): return "read-body" if ctx else "locate"
        if mode == "files_with_matches": return "list-files"
        return "call-sites"
    if "<<HEREDOC" in seg or re.match(r"(\S*python\S*|cat\s*>|tee)\b", seg): return "not-a-search"
    if not re.search(r"\b(grep|rg|egrep)\b", seg): return "not-a-search"
    if re.search(r"\|\s*wc\b|\s-c\b|--count", seg): return "count"
    if re.search(r"\s-l\b|-\w*l\w*\s", seg) and not re.search(r"-\w*n", seg): return "list-files"
    q = re.search(r"""(grep|rg|egrep)\s+(?:-\S+\s+)*(['"])(.*?)\2""", seg); pat = q.group(3) if q else ""
    if re.search(r"(def|class|function|struct)\s*(\\\||$)", pat) or re.fullmatch(r"\^?\s*(def|class)\s*", pat.strip()): return "list-file-symbols"
    if re.search(r"\b(def|class|function|struct)\s+\\?\(?\w", seg):
        return "read-body" if re.search(r"\s-[ABC]\s*\d|\s-[ABC]\d|--(after|before|context)", seg) else "locate"
    if re.search(r"\.(md|txt|toml|json|ya?ml|cfg|ini)\b|\.gitignore|AGENTS|CLAUDE", seg): return "literal-text"
    if re.search(r"\s-[ABC]\s*\d|\s-[ABC]\d", seg): return "read-body"
    if re.search(r"\s-\w*l\b", seg.split("|")[0]): return "list-files"
    if re.match(r"\^\w", pat) or re.search(r"\\\|\^\w", pat): return "locate"
    ops = [w for w in seg.split("|")[0].split()[1:] if not w.startswith("-") and w.strip("'\"") != pat]
    if len(ops) == 1 and re.search(r"\.\w+$", ops[0]) and "*" not in ops[0]: return "in-file-lines"
    if re.search(r"\|\s*grep\s+-v", seg): return "filter"
    return "call-sites"
MATCH = {("read-body", "read-answer"): "match", ("locate", "read-answer"): "match (larger than asked)",
         ("call-sites", "pack"): "match", ("locate", "pack"): "partial (Defined-at line only)", ("filter", "pack"): "partial (callers, not filtered)", ("in-file-lines", "pack"): "partial (repository callers for a one-file search)"}
# hand review: the segment that triggered the answer is a later grep in the command
OVERRIDE = {729: ("list-file-symbols", 'grep -n "pack" devkb/packs.py | grep "def \\|class " | head'), 661: ("filter", 'grep -rn "repo_path" tests/*.py | grep -v "def \\|import" | head -5'),
            662: ("filter", 'grep -rn "\\brepo_path\\b" tests/test_boundaries.py | head -5'),
            808: ("literal-text", 'grep -n "stats" devkb/cli.py | head')}
out = []; tab = collections.Counter(); chars = collections.Counter()
for x in rows:
    if x["kind"] == "none": continue
    ans = "read-answer" if x["kind"] == "read-answer" else "pack"
    names = answered_names(x["answer"])
    if x["tool"] == "Grep":
        it = intent("", x["input"]); seg = x["input"].get("pattern")
    else:
        ss = segs(x["input"]["command"])
        hit = [s for s in ss if any(re.search(rf"\b{re.escape(n.split('.')[-1])}\b", s, re.I) for n in names)] or ["<HEREDOC body>" if "<<" in x["input"]["command"] else ss[0]]
        seg = hit[0]; it = intent(seg) if seg != "<HEREDOC body>" else "not-a-search"
    if x["i"] in OVERRIDE: it, seg = OVERRIDE[x["i"]]
    v = MATCH.get((it, ans), "mismatch")
    out.append({"i": x["i"], "intent": it, "answer": ans, "verdict": v, "names": names, "segment": seg[:200], "chars": x["chars"]})
    tab[(it, ans, v)] += 1; chars[v.split()[0]] += x["chars"]
json.dump(out, open("labels.json", "w"), indent=1)
for k, n in sorted(tab.items(), key=lambda kv: -kv[1]): print(f"{n:4d}  intent={k[0]:18s} answer={k[1]:12s} {k[2]}")
tot = sum(tab.values()); vs = collections.Counter(); [vs.update({k[2].split()[0]: n}) for k, n in tab.items()]
print("total", tot, dict(vs), {k: f"{v} chars" for k, v in chars.items()})
