"""How agents search and how they pipe devkb output, from the recorded devkb-arm runs. One script for two claims that were first made
ad hoc and did not reproduce under audit: the share of greps the graph could answer, and what `| head -N` on devkb output did.

  greps       every grep/rg pattern (quoted or not, anywhere in a chain; bench/policy/searches.py) classified by what it asks:
              a distinctive graph symbol (a name with `_`, inner capitals or nine letters or more, defined in the base graph),
              a plain word that is also a symbol, a name the graph does not define, or text/regex. The shares sum to 100%.
  head        devkb navigation commands piped through `head -N`: a command's whole result shorter than N lines proves head cut
              nothing; a longer one may or may not have been cut (a chain's output cannot be attributed), so the proven share is a
              lower bound.
Usage: nav_habits.py [TICKET ...]"""
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import replay_queries as rq  # noqa: E402
import searches  # noqa: E402
import storybench as sb  # noqa: E402
from devkb.process_api import ProcessAPI  # noqa: E402
from devkb.read_tools import ReadTools  # noqa: E402

KEEP = Path.home() / ".cache" / "devkb" / "replay"
DK = str(ROOT / ".venv" / "bin" / "devkb")
_T: dict = {}


def names(ticket):
    if ticket not in _T:
        r = ReadTools(ProcessAPI(str(rq.base_graph(ticket, KEEP, DK))))
        r._tables()
        _T[ticket] = r._by_name
    return _T[ticket]


def classify(ticket: str, pattern: str) -> str:
    alts = [a.strip() for a in re.split(r"\\\||(?<!\\)\|", pattern) if a.strip()]
    terms = []
    for a in alts:
        m = re.fullmatch(r"(?:\^?\s*)?(?:async\s+)?(?:def|class)?\s*\\?b?([A-Za-z_]\w+)\\?b?\s*(?:\\?\(|=|\\?:)?.*", a)
        if not m:
            return "text, phrase or regex"
        terms.append(m[1])
    known = [t for t in terms if t.lower() in names(ticket)]
    if not known:
        return "a name the graph does not define (a field, keyword or word)"
    return "a distinctive graph symbol" if any(sb.distinctive(t) for t in known) else "a plain word that is also a symbol"


def main(tickets: list[str]) -> None:
    greps, calls_total = collections.Counter(), 0
    pipes = collections.Counter()
    for f in sorted((HERE / "runs").glob("p*-*-r*/stream.jsonl")):
        m = re.match(r"p(\d+)-(\w+)-r\d", f.parent.name)
        if not m or m[1] not in tickets or "none" in m[2]:
            continue
        calls, res = [], {}
        for line in open(f):
            if not line.startswith("{"):
                continue
            try:
                e = json.loads(line)
            except ValueError:                                  # a cut-off run can end mid-line
                continue
            if e.get("type") == "assistant":
                calls += [b for b in e["message"].get("content", []) if b.get("type") == "tool_use"]
            elif e.get("type") == "user" and isinstance(e["message"].get("content"), list):
                for b in e["message"]["content"]:
                    if b.get("type") == "tool_result":
                        t = b.get("content")
                        res[b["tool_use_id"]] = t if isinstance(t, str) else " ".join(x.get("text", "") for x in t if isinstance(x, dict))
        for b in calls:
            for p in searches.searches_in(b["name"], b.get("input") or {}):
                greps[classify(m[1], p)] += 1
            if b["name"] == "Bash":
                c = b["input"].get("command", "")
                segs = [s for s in searches._segments(c)]
                dk = [s for s in segs if re.search(r"\bdevkb\s+(symbol|outline|uses|pack|docs)\b", s)]
                if not dk or "|" not in c:
                    continue
                hd = re.search(r"\|\s*head\s+(?:-n\s*)?-?(\d+)", c)
                if not hd:
                    pipes["piped to something else (grep, sed, tail, wc...)"] += 1
                    continue
                n = int(hd[1])
                out = res.get(b["id"], "")
                lines = out.count("\n") + 1
                if lines < n:                                                   # the whole result is shorter than N: head cut nothing
                    pipes["head cut nothing (the whole result is shorter than N lines)"] += 1
                else:
                    pipes["head: the result is N lines or more, so it may have been cut (not attributable in a chain)"] += 1
    tot = sum(greps.values())
    print(f"{tot} grep/rg patterns in the devkb-arm runs")
    for k, v in greps.most_common():
        print(f"  {v:4}  {100 * v / tot:5.1f}%  {k}")
    print(f"\ndevkb navigation commands with a pipe: {sum(pipes.values())}")
    for k, v in pipes.most_common():
        print(f"  {v:4}  {k}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["118", "120", "203", "205", "286", "287"])
