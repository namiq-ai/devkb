"""Offline replay of the guardrail's staleness rule on recorded runs (no model runs).

The live rule (scripts/devkb_guardrail.py graph_stale): once any code file in the search's scope has changed since the graph
was built, no graph answer is given. In a coding task the agent edits early, so after its first edit nothing is answered.
The alternative replayed here: the graph is stale *for this search* only if a file the answer depends on changed, that is a
file that defines one of the names or uses it.

For every grep/rg/Grep search of the devkb-arm runs, in the run's order, with the files the run had edited by then:
  before first edit      the live rule already allows an answer
  after, no name         no graph symbol among the search's names: no answer either way
  after, a name          the live rule withholds; the alternative answers when none of the files the names are defined or
                         used in was edited, and otherwise still withholds (those are the files to read)
Usage: stale_replay.py [TICKET ...]   (default: 118 120 203 205 286 287)"""
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import replay_queries as rq  # noqa: E402
import searches  # noqa: E402
from devkb import misses  # noqa: E402
from devkb.process_api import ProcessAPI  # noqa: E402
from devkb.read_tools import ReadTools  # noqa: E402

WORK = Path.home() / ".cache" / "devkb" / "policy-work"
KEEP = Path.home() / ".cache" / "devkb" / "replay"
DK = str(ROOT / ".venv" / "bin" / "devkb")
CODE = (".py", ".h", ".hh", ".hpp", ".c", ".cc", ".cpp", ".cxx", ".ts", ".tsx", ".js")
GREP = re.compile(r"(?:^|[\s;|&(])(?:grep|rg|egrep)\b([^|;&\n]*)")
_cache: dict = {}


def tables(ticket: str):
    if ticket not in _cache:
        d = rq.base_graph(ticket, KEEP, DK)
        r = ReadTools(ProcessAPI(str(d)))
        r._tables()
        _cache[ticket] = (d, r)
    return _cache[ticket]


def files_of(ticket: str, name: str) -> tuple[set[str], set[str]]:
    """(files that define `name`, files that use it); both empty when the graph defines nothing of that name."""
    d, r = tables(ticket)
    ids = r._by_name.get(name.lower(), [])
    if not ids or len(name) < 4 and "_" not in name:
        return set(), set()
    defs = {r.file[i] for i in ids}
    p = subprocess.run([DK, "uses", name, "--project", str(d)], capture_output=True, text=True, timeout=60)
    used = set(re.findall(r"^\s*(?:defined: )?([\w./-]+\.\w+)[: ]", p.stdout, re.M)) | set(re.findall(r"([\w./-]+\.(?:py|h|cc|cpp|ts|md))[: ]\d", p.stdout))
    return defs, used


def run_calls(stream: Path):
    for line in open(stream):
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except ValueError:                                  # a cut-off run can end mid-line
            continue
        if e.get("type") == "assistant":
            for b in e["message"].get("content", []):
                if b.get("type") == "tool_use":
                    yield b["name"], b.get("input") or {}


def main(tickets: list[str]) -> None:
    tot = collections.Counter()
    for f in sorted((HERE / "runs").glob("p*-*-r*/stream.jsonl")):
        m = re.match(r"p(\d+)-(\w+)-r\d", f.parent.name)
        if not m or m[1] not in tickets or "none" in m[2]:
            continue
        run, edited = f.parent.name, set()
        for name, inp in run_calls(f):
            if searches.writes_code(name, inp):                       # an Edit, or a Bash write: sed -i, a heredoc, a redirect
                if "file_path" in inp:
                    edited.add(rq.rel(str(inp["file_path"]), run))
                else:                                                  # a shell write names its files in the command, usually
                    named = {rq.rel(x, run) for x in re.findall(r"[\w./-]+\.(?:py|h|hh|hpp|c|cc|cpp|cxx|ts|tsx|js|sh)\b", inp.get("command", ""))}
                    edited |= named or {f"<bash write {len(edited)}>"}
                continue
            for p in searches.searches_in(name, inp):
                tot["searches"] += 1
                names = misses.navigation_names(p, "both")[:3]
                known = [(n, *files_of(m[1], n)) for n in names]
                known = [k for k in known if k[1]]
                if not edited:
                    tot["before first edit"] += 1
                    tot["before first edit, with a graph symbol"] += bool(known)
                    continue
                tot["after first edit"] += 1
                if not known:
                    tot["after, no graph symbol"] += 1
                    continue
                tot["after, with a graph symbol (live rule withholds)"] += 1
                dep = set().union(*[k[1] | k[2] for k in known])
                hit = {e for e in edited if e in dep}
                if any(e.startswith("<bash write") for e in edited):      # the files a shell write touched are unknown: do not claim a name is safe
                    hit |= {"<bash write>"}
                if hit:
                    tot["  still withheld: a file the names depend on was edited"] += 1
                else:
                    tot["  answerable: none of the files the names depend on was edited"] += 1
    for k, v in tot.items():
        print(f"{v:5}  {k}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["118", "120", "203", "205", "286", "287"])
