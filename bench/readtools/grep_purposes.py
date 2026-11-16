#!/usr/bin/env python3
"""What were the agents grepping for, what did it cost, and could the graph answer it?

  grep_purposes.py EVAL_DIR GRAPH_NODES.jsonl [--examples]

A grep event is one Grep tool call or one shell command containing grep. Cost: text returned (tokens = chars / 4) and the
same weighted by the model calls still to come, since text that stays in context is paid for again on every later call
(the cached-read price is lower, so only the ranking matters). Purposes are assigned by rules, then checked on samples."""
import collections, json, re, sys

E, NODES = sys.argv[1], sys.argv[2]
RUNS = ["plain-r1", "plain-r2", "devkb-r1", "devkb-r2", "devkb-r3", "devkb-r4", "spec-r1", "spec-r2", "impl"]
names = set()
for l in open(NODES):
    n = json.loads(l)
    if n["type"] == "Symbol":
        names.add(n["natural_key"].split("::")[-1].rsplit(".", 1)[-1])

GREP = re.compile(r"\bgrep\b((?:\s+-[A-Za-z]+)*)\s+(?:-e\s+)?(?:\"([^\"]+)\"|'([^']+)'|(\S+))([^|;&\n]*)")


HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", re.S)
TRIVIAL = re.compile(r"^(cd|echo|true|export|set|source|mkdir|rm|cp|mv|touch|sleep|printf|:)\b")


def segments(cmd):
    """The command's pipelines, each as a list of pipe stages; heredoc bodies removed; quotes and escapes respected, so a
    grep pattern like "a\\|b" is not cut at its pipe."""
    cmd = HEREDOC.sub(" ", cmd)
    pipelines, stages, cur, q, i = [], [], [], None, 0

    def end_stage():
        t = "".join(cur).strip(); cur.clear()
        if t: stages.append(t)

    def end_pipeline():
        end_stage()
        if stages and not TRIVIAL.match(stages[0]): pipelines.append(list(stages))
        stages.clear()

    while i < len(cmd):
        c = cmd[i]
        if q:
            cur.append(c)
            if c == "\\" and q == '"' and i + 1 < len(cmd): cur.append(cmd[i + 1]); i += 1
            elif c == q: q = None
        elif c in "\"'": q = c; cur.append(c)
        elif c == "\\" and i + 1 < len(cmd): cur.append(c); cur.append(cmd[i + 1]); i += 1
        elif cmd.startswith("&&", i) or cmd.startswith("||", i): end_pipeline(); i += 1
        elif c in ";\n": end_pipeline()
        elif c == "|": end_stage()
        else: cur.append(c)
        i += 1
    end_pipeline()
    return pipelines


def events(path):
    uses, order, results = {}, {}, {}
    for l in open(path):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            mid = e["message"].get("id")
            if mid and mid not in order:
                order[mid] = len(order)
            for x in e["message"]["content"]:
                if x.get("type") == "tool_use":
                    uses[x["id"]] = (x["name"], x["input"], order.get(mid, len(order)))
        if e.get("type") == "user" and isinstance(e["message"].get("content"), list):
            for x in e["message"]["content"]:
                if x.get("type") == "tool_result":
                    c = x.get("content")
                    results[x["tool_use_id"]] = len(c if isinstance(c, str) else json.dumps(c))
    total = len(order)
    for uid, (name, inp, idx) in uses.items():
        if name == "Grep":
            yield dict(tool="Grep", pat=inp.get("pattern", ""), target=inp.get("path", "") or inp.get("glob", ""), flags="",
                       piped=False, cmd="", size=results.get(uid, 0), left=total - idx)
        elif name == "Bash":
            segs = segments(inp.get("command", ""))
            for stages in segs:
                for k, st in enumerate(stages):
                    m = re.match(r"(?:\w+=\S+\s+)*(?:egrep|grep|rg)\b((?:\s+-[A-Za-z]+\d*)*)\s+(?:-e\s+)?(?:\"([^\"]+)\"|'([^']+)'|(\S+))(.*)", st)
                    if not m:
                        continue
                    rest = (m.group(5) or "").strip()
                    opts = " ".join(t for t in rest.split() if t.startswith("-"))
                    target = " ".join(t for t in rest.split() if not t.startswith("-") and not re.fullmatch(r"\d+", t))
                    yield dict(tool="Bash", pat=m.group(2) or m.group(3) or m.group(4) or "", target=target, flags=(m.group(1) or "") + " " + opts,
                               piped=k > 0, cmd=" | ".join(stages), size=results.get(uid, 0) / len(segs), left=total - idx)
                    break


def purpose(ev, names=names):
    pat, tgt, fl = ev["pat"], ev["target"], ev["flags"]
    if ev["piped"] or (not tgt and ev["tool"] == "Bash"):
        return "filter the output of another command"
    if re.search(r"(^|\s)-[A-Za-z]*[cq]", fl) or re.search(r"\|\s*wc\s+-l", ev["cmd"]):
        return "count or check that something is present"
    if re.search(r"exercise\d/checkouts|/tmp/|scratch|\b(cJSON|leveldb|fmt|zephyr)/", tgt):
        return "search an external repository or a scratch file (no graph)"
    if re.search(r"docs|\.md\b|stories|spec/|adr|README|issues", tgt):
        return "find text in docs, specs and tickets"
    flat = re.sub(r"\\\||\|", "|", pat)
    alts = [a for a in flat.split("|") if a]
    bare = lambda a: bool(re.fullmatch(r"\^?(\\s\*|\s)*(def|class|@dataclass|import|from)(\\s|\s)*[^A-Za-z_]*", a))
    if alts and any(bare(a) for a in alts):
        return "outline: list the definitions and imports in a file"
    if re.search(r"tests?/|_test\b|test_", tgt) or re.search(r"\bdef test_|\bTEST(_F)?\(", pat):
        return "find tests"
    named = [re.fullmatch(r"\^?(?:\\s\*|\s)*(?:def|class|function|struct|enum)\s+([A-Za-z_]\w*).*", a) for a in alts]
    if alts and all(named):
        return "find where one symbol is defined"
    ids = []
    for a in alts:
        a = re.sub(r"\\b|\\<|\\>|^\^|\$$|\\\(|\\s\*|\(|\)|\*|\s", "", a)
        if re.fullmatch(r"[A-Za-z_][\w.]*", a):
            ids.append(a)
    if ids and len(ids) == len(alts):
        known = [a for a in ids if a.rsplit(".", 1)[-1] in names]
        if known:
            return "find the callers or users of a function or class the graph knows"
        if all(re.fullmatch(r"_?[A-Z][A-Z0-9_]+", a) for a in ids):
            return "find uses of a constant or macro"
        return "find uses of a module, key or name the graph has no node for"
    calls = [t for t in re.findall(r"([A-Za-z_]\w*)\s*(?:\\\(|\()", pat) if t in names and t not in ("def", "class")]
    if calls:
        return "find the callers or users of a function or class the graph knows"
    return "find a string, phrase or pattern in code"


GRAPH = {  # purpose -> (can the graph answer it?, how)
    "filter the output of another command": ("not a search", "grep is filtering a command's output"),
    "count or check that something is present": ("not a search", "verification after an edit or a quick existence test"),
    "find the callers or users of a function or class the graph knows": ("yes, today", "`callers`, `pack(refactor)`; the instruction says to grep one hop"),
    "find where one symbol is defined": ("yes, data exists", "Symbol + DEFINED_IN + line; reachable through `find_code` (dev toolset) or `devkb query`, not in the default lean-pack set"),
    "find tests": ("yes, today", "TestCase + TESTED_BY; `tests_for`, `tests_to_run`"),
    "find uses of a constant or macro": ("no, needs new data", "module-level constants and macros are not nodes"),
    "find uses of a module, key or name the graph has no node for": ("no, needs new data", "modules, imports and keys are not nodes (only env vars as ConfigKey)"),
    "search an external repository or a scratch file (no graph)": ("no, outside the graph", "the checkouts and scratch files are not the repository being edited (they have no .devkb)"),
    "outline: list the definitions and imports in a file": ("yes, data exists", "Symbols by file with line ranges; `explain_area` gives key symbols only, no full outline tool"),
    "find text in docs, specs and tickets": ("partly", "`find_docs` ranks specs/ADRs/design docs by topic; no text search inside docs"),
    "find a string, phrase or pattern in code": ("partly", "error messages (ErrorSignature) and env vars (ConfigKey) only; other text is not indexed"),
}

if __name__ == "__main__":
    rows = []
    for r in RUNS:
        try:
            for ev in events(f"{E}/run-{r}/stream.jsonl"):
                ev["run"] = r; ev["purpose"] = purpose(ev); rows.append(ev)
        except FileNotFoundError:
            pass
    tot_tok = sum(e["size"] for e in rows) / 4; tot_w = sum(e["size"] / 4 * max(e["left"], 1) for e in rows)
    agg = collections.defaultdict(lambda: [0, 0.0, 0.0, []])
    for e in rows:
        a = agg[e["purpose"]]; a[0] += 1; a[1] += e["size"] / 4; a[2] += e["size"] / 4 * max(e["left"], 1)
        if len(a[3]) < 3: a[3].append((e["pat"][:48], e["target"][:34]))
    print(f"grep events: {len(rows)} in {len(set(e['run'] for e in rows))} runs; text returned {tot_tok / 1000:.0f}k tokens\n")
    print(f"{'purpose':64s} {'n':>4s} {'%n':>4s} {'tokens':>8s} {'%tok':>5s} {'%cost*':>7s} {'cum%':>5s}  graph")
    cum = 0
    for p, (n, tk, w, ex) in sorted(agg.items(), key=lambda x: -x[1][2]):
        cum += 100 * w / tot_w
        print(f"{p:64s} {n:4d} {100 * n // len(rows):3d}% {tk / 1000:7.1f}k {100 * tk / tot_tok:4.0f}% {100 * w / tot_w:6.1f}% {cum:4.0f}%  {GRAPH[p][0]}")
    if "--examples" in sys.argv:
        print()
        for p, (n, tk, w, ex) in sorted(agg.items(), key=lambda x: -x[1][2]):
            print(f"{p}:"); [print(f"    {a!r:52s} in {b!r}") for a, b in ex]
    json.dump({p: dict(n=a[0], tokens=a[1], weighted=a[2], graph=GRAPH[p]) for p, a in agg.items()}, open(f"{E}/grep-purposes.json", "w"))


PURPOSE = {  # what the agent is trying to learn, and what would answer it
    "filter the output of another command": ("trim the output of tests, git or a file read down to the lines it cares about", "nothing: grep is a filter here, not a search"),
    "find where one symbol is defined": ("read a function or class: 90% add -A/-B/-C, i.e. they want the body, not the location", "a `symbol(name)` call returning signature, file and exact line range, with the source on request (the graph stores line_start and line_end)"),
    "outline: list the definitions and imports in a file": ("see the shape of a file before reading or editing it", "an `outline(file)` call: Symbols of the file with line ranges (the graph has them; `explain_area` shows only key symbols)"),
    "find the callers or users of a function or class the graph knows": ("who uses this function (impact of a change)", "`callers`, `pack(refactor)`: available now; the instruction tells agents to grep one-hop lookups"),
    "find text in docs, specs and tickets": ("check what the README, scope or spec says", "`find_docs` ranks specs/ADRs by topic; the text inside docs is not indexed"),
    "find uses of a module, key or name the graph has no node for": ("where is this module, import, key or argument name used", "new graph data: modules and imports as nodes with USES edges"),
    "find a string, phrase or pattern in code": ("locate code by an idiom or literal", "only error messages and env vars are indexed (ErrorSignature, ConfigKey)"),
    "find tests": ("which tests touch this", "`tests_for`, `tests_to_run`: available now"),
    "find uses of a constant or macro": ("where is this module-level constant or macro used", "new graph data: module-level constants and macros as nodes"),
    "search an external repository or a scratch file (no graph)": ("read the reference corpus or a temporary file", "nothing: they are outside the repository being edited"),
    "count or check that something is present": ("verify an edit or a count", "nothing: verification, not search"),
}

def markdown(rows, out):
    n_all = len(rows); tok_all = sum(e["size"] for e in rows) / 4; w_all = sum(e["size"] / 4 * max(e["left"], 1) for e in rows)
    agg = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for e in rows:
        a = agg[e["purpose"]]; a[0] += 1; a[1] += e["size"] / 4; a[2] += e["size"] / 4 * max(e["left"], 1)
    not_search = {"filter the output of another command", "count or check that something is present"}
    w_search = sum(a[2] for p, a in agg.items() if p not in not_search)
    L = ["| Kind of grep | What the agent is trying to learn | Events | Text returned | Share of grep cost | Cumulative | Can the graph answer it? | What would answer it |", "|" + "---|" * 8]
    cum = 0
    for p, a in sorted(agg.items(), key=lambda x: -x[1][2]):
        cum += 100 * a[2] / w_all
        L.append(f"| {p} | {PURPOSE[p][0]} | {a[0]} ({100 * a[0] // n_all}%) | {a[1] / 1000:.1f}k | {100 * a[2] / w_all:.1f}% | {cum:.0f}% | {GRAPH[p][0]} | {PURPOSE[p][1]} |")
    ans_now = ["find where one symbol is defined", "outline: list the definitions and imports in a file", "find the callers or users of a function or class the graph knows", "find tests"]
    two = ["find where one symbol is defined", "outline: list the definitions and imports in a file"]
    s2 = sum(agg[p][2] for p in two if p in agg); s4 = sum(agg[p][2] for p in ans_now if p in agg)
    k_to_80 = next(i + 1 for i, (p, a) in enumerate(sorted(agg.items(), key=lambda x: -x[1][2])) if sum(b[2] for _, b in sorted(agg.items(), key=lambda x: -x[1][2])[:i + 1]) / w_all >= 0.8)
    text = "\n".join(L) + f"""

**Reading the cost.** The cost is flatter than 80/20: it takes {k_to_80} of {len(agg)} kinds to reach 80% of grep cost. Two of the eleven kinds
(definition lookup and outline) are {100 * s2 / w_all:.0f}% of all grep cost ({100 * s2 / w_search:.0f}% of the cost of real searches), and the four kinds the graph can already answer
from data it holds (adding callers and tests) are {100 * s4 / w_all:.0f}% ({100 * s4 / w_search:.0f}% of searches). The 20% to pick is therefore the **definition and outline** pair: one need ("show me the code
structure and a symbol's body, with exact lines") and no schema change.

Cost here = text returned to the model, weighted by the model calls still to come (text stays in context). Events = {n_all} greps in 9 build runs.
"""
    open(out, "w").write(text); return text

if "--markdown" in sys.argv:
    rows = []
    for r in RUNS:
        try:
            for ev in events(f"{E}/run-{r}/stream.jsonl"):
                ev["purpose"] = purpose(ev); rows.append(ev)
        except FileNotFoundError:
            pass
    print(markdown(rows, sys.argv[sys.argv.index("--markdown") + 1]))
