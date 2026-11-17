"""Shortest text path from each named method to a target, in a C# repository's production code: the check behind a
question's `truth_property_reads` (bench/cs_value.py).

  python bench/cs_reach_text.py REPO GRAPH_DIR TARGET NAME[,NAME...]

GRAPH_DIR is a devkb graph of REPO (method line ranges come from it). An edge A -> B when A's body contains the
identifier B, a call or a property read. A name defined more than 4 times in production code is not followed (a
collision guard), so a found path is a candidate, not a proof: every path it prints is to be read in the source by
hand before a name is added to a truth. "no path" means none within these limits.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cs_truth_from_roslyn import is_production  # noqa: E402

MAXDEF = 4
TYPES = ("class", "struct", "interface", "record", "enum")


def main() -> int:
    root, graph, target, names = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4].split(",")
    defs = []
    for line in (graph / "nodes.jsonl").open():
        n = json.loads(line)
        if n["type"] != "Symbol":
            continue
        f, _, qn = n["natural_key"].partition("::")
        p = n["properties"]
        if f.endswith(".cs") and is_production(f) and p.get("kind") not in TYPES:
            defs.append((f, qn, p["line_start"], p["line_end"]))
    short = lambda qn: qn.split(".")[-1]  # noqa: E731
    count = collections.Counter(short(d[1]) for d in defs)
    files: dict[str, list[str]] = {}
    users = collections.defaultdict(set)              # identifier -> definitions whose body uses it
    for i, (f, _qn, a, b) in enumerate(defs):
        if f not in files:
            files[f] = (root / f).read_text(errors="replace").splitlines()
        for tok in set(re.findall(r"[A-Za-z_]\w*", "\n".join(files[f][a:b]))):   # the body, after the header line
            users[tok].add(i)
    prev: dict = {target: None}
    todo = collections.deque([target])
    while todo:
        r = todo.popleft()
        if r != target and count[r] > MAXDEF:
            continue
        for i in users.get(r, ()):
            s = short(defs[i][1])
            if s not in prev:
                prev[s] = (r, i)
                todo.append(s)
    for w in names:
        if w not in prev:
            print(f"no path   {w} (defined {count[w]}x)")
            continue
        chain, x = [], w
        while prev[x]:
            r, i = prev[x]
            chain.append(f"{defs[i][1]} [{defs[i][0]}:{defs[i][2]}]")
            x = r
        print(f"REACHES   {w} (defined {count[w]}x): " + " -> ".join(chain) + f" -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
