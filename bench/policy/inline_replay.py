"""Offline upper bound for inline context (a PostToolUse answer on Read/Edit of a file): how many of the agent's later
navigation calls were already covered by the `pack file` of a file it had opened by then? No model runs.

For each devkb-arm run, in order, track the files the agent has Read or Edited. A later navigation call is covered when
  - a Read/sed/head/cat of a file the pack lists (a dependent, a caller's file or a test), or
  - a grep/rg whose names are all defined in an opened file or named in an opened file's pack.
Both are upper bounds: the answer would still have to be read, and a pack is only as complete as its Coverage says.
Usage: inline_replay.py [TICKET ...]"""
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

KEEP = Path.home() / ".cache" / "devkb" / "replay"
DK = str(ROOT / ".venv" / "bin" / "devkb")
CODE = (".py", ".h", ".hh", ".hpp", ".c", ".cc", ".cpp", ".cxx", ".ts", ".tsx", ".js")
GREP = re.compile(r"(?:^|[\s;|&(])(?:grep|rg|egrep)\b([^|;&\n]*)")
READ = re.compile(r"\b(?:sed\s+-n\s+\S+|head\s+(?:-n\s*)?-?\d+|tail\s+(?:-n\s*)?\+?\d+|cat)\s+([\w./-]+\.\w+)")
_pack: dict = {}
_tab: dict = {}


def tab(ticket):
    if ticket not in _tab:
        r = ReadTools(ProcessAPI(str(rq.base_graph(ticket, KEEP, DK))))
        r._tables()
        _tab[ticket] = r
    return _tab[ticket]


def pack_of(ticket: str, f: str) -> tuple[set, set, int]:
    """(files named by `pack file F`, names it names, its size in characters)."""
    k = (ticket, f)
    if k not in _pack:
        d = rq.base_graph(ticket, KEEP, DK)
        p = subprocess.run([DK, "pack", "--project", str(d), "file", f], capture_output=True, text=True, timeout=120).stdout
        files = set(re.findall(r"[\w./-]+\.(?:py|h|hh|hpp|c|cc|cpp|cxx|ts|tsx|js|md)", p))
        names = set(re.findall(r"`([A-Za-z_][\w.:]*)`", p)) | set(re.findall(r"\b([A-Za-z_]\w{3,})\(", p))
        names |= {n.split(".")[-1].split("::")[-1] for n in names}
        r = tab(ticket)
        names |= {r.short[i] for i in r.ids if r.file[i] == f}
        _pack[k] = (files, names, len(p))
    return _pack[k]


def main(tickets: list[str]) -> None:
    tot = collections.Counter()
    for f in sorted((HERE / "runs").glob("p*-*-r*/stream.jsonl")):
        m = re.match(r"p(\d+)-(\w+)-r\d", f.parent.name)
        if not m or m[1] not in tickets or "none" in m[2]:
            continue
        run, opened, calls = f.parent.name, [], []
        for line in open(f):
            if line.startswith("{"):
                try:
                    e = json.loads(line)
                except ValueError:                                  # a cut-off run can end mid-line
                    continue
                if e.get("type") == "assistant":
                    calls += [(b["name"], b.get("input") or {}) for b in e["message"].get("content", []) if b.get("type") == "tool_use"]
        tot["runs"] += 1
        for name, inp in calls:
            fp = rq.rel(str(inp.get("file_path", "")), run) if name in ("Read", "Edit", "Write", "MultiEdit") else ""
            targets, kind = [], None
            if name == "Read" and fp:
                targets, kind = [fp], "read"
            elif name == "Bash":
                c = inp.get("command", "")
                if re.search(r"\bdevkb\s", c) and not searches.grep_patterns(c):
                    continue
                targets = [rq.rel(x, run) for x in READ.findall(c)]
                kind = "read" if targets else None
                for pat in searches.grep_patterns(c):
                    kind, targets = "grep", misses.navigation_names(pat, "both")[:3]
            elif name == "Grep":
                kind, targets = "grep", misses.navigation_names(inp.get("pattern", ""), "both")[:3]
            if kind and targets and (kind == "grep" or any(t.endswith(CODE) for t in targets)):
                tot["navigation calls"] += 1
                tot[f"  {kind} calls"] += 1
                cover = [pack_of(m[1], o) for o in opened if o.endswith(CODE)]
                if kind == "read":
                    # a file the pack names that the agent has not opened: a re-read of an opened file is not something a pack replaces,
                    # and a pack that names a file does not replace reading it (an audit: 91 of the first 144 were re-reads)
                    hit = any(t in fl and t not in opened for t in targets for fl, _n, _s in cover)
                else:
                    hit = bool(targets) and all(any(n in ns for _f, ns, _s in cover) for n in targets)
                if opened and hit:
                    tot[f"  {kind} covered by an opened file's pack"] += 1
                    tot["covered"] += 1
                if opened:
                    tot["after the first file was opened"] += 1
            if fp and fp.endswith(CODE) and fp not in opened:
                opened.append(fp)
                tot["files opened"] += 1
                tot["pack characters if answered inline (sum)"] += pack_of(m[1], fp)[2]
    for k, v in tot.items():
        print(f"{v:7}  {k}")
    r, n = tot["runs"], tot["navigation calls"]
    print(f"\nper run: {n / r:.1f} navigation calls, {tot['covered'] / r:.1f} covered, {tot['files opened'] / r:.1f} files opened, "
          f"{tot['pack characters if answered inline (sum)'] / r / 4:.0f} tokens of packs if every opened file were answered inline")


if __name__ == "__main__":
    main(sys.argv[1:] or ["118", "120", "203", "205", "286", "287"])
