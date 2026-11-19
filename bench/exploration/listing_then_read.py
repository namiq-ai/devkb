"""#168 (SPEC-DKB-006 C3): is listing a code folder followed by reads in it often enough to justify a folder outline?

Reads Claude Code session transcripts (stream-json, one `stream.jsonl` per run directory). For every listing of a
folder (`ls DIR`, `tree DIR`, `ls` = the working directory, or the Glob tool), counts the reads of files under that
folder in the next WINDOW tool calls: `sed -n`, `cat`, `head`, `tail` and the Read tool. A read is "locating" when it
follows a `grep -n` for a definition in the same window (the agent was looking for one symbol, which `symbol`
answers without any listing).

    python3 bench/exploration/listing_then_read.py RUNS_DIR [--window 5] [--json]

Standard library only. Paths are compared as written, relative to the session's working directory, after `cd`.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import shlex
from collections import Counter
from pathlib import Path

CODE = {".py", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".cs", ".ts", ".tsx", ".js", ".go", ".rs", ".java"}
READERS = ("sed", "cat", "head", "tail")


def stages(cmd: str) -> list[list[str]]:
    cmd = re.sub(r"<<-?\s*'?(\w+)'?.*?\n\1\b", "", cmd, flags=re.S)
    out = []
    for part in re.split(r"&&|\|\||;|\||\n", cmd):
        try:
            words = shlex.split(part)
        except ValueError:
            continue
        if words:
            out.append(words)
    return out


def norm(cwd: str, p: str) -> str:
    return posixpath.normpath(posixpath.join(cwd, p))


def rel(root: str, p: str) -> str:
    """A path inside the session's working directory, relative to it, so absolute Read paths and relative listings
    compare (#210)."""
    if root and (p == root or p.startswith(root.rstrip("/") + "/")):
        return posixpath.relpath(p, root)
    return p


def events(stream: Path):
    """(kind, folder-or-file, extra) per relevant tool call, in order; kind in list | read | defgrep | other."""
    root = ""
    for line in open(stream, errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            root = e.get("cwd") or ""
        m = e.get("message")
        if not isinstance(m, dict):
            continue
        for x in m.get("content") or []:
            if not isinstance(x, dict) or x.get("type") != "tool_use":
                continue
            inp = x.get("input") or {}
            if x["name"] == "Glob":
                yield "list", rel(root, norm(".", inp.get("path") or ".")), "glob"
                continue
            if x["name"] == "Read":
                yield "read", rel(root, norm(".", inp.get("file_path", ""))), "Read"
                continue
            if x["name"] != "Bash":
                yield "other", "", x["name"]
                continue
            cwd, any_ = ".", False
            for w in stages(inp.get("command", "")):
                head = w[0].rsplit("/", 1)[-1]
                if head == "cd" and len(w) > 1:
                    cwd = norm(cwd, w[1])
                elif head in ("ls", "tree"):
                    dirs = [a for a in w[1:] if not a.startswith("-") and not re.search(r"[<>&~*]", a)] or ["."]
                    for d in dirs:
                        any_ = True
                        yield "list", rel(root, norm(cwd, d)), head
                elif head in READERS:
                    files = [a for a in w[1:] if not a.startswith("-") and Path(a).suffix.lower() in CODE]
                    for f in files:
                        any_ = True
                        yield "read", rel(root, norm(cwd, f)), head
                elif head in ("grep", "rg") and any(a.startswith("-") and "n" in a for a in w[1:]) \
                        and re.search(r"\b(def|class|struct|fn|func|function)\b", " ".join(w[1:])):
                    any_ = True
                    yield "defgrep", cwd, head
            if not any_:
                yield "other", "", "Bash"


def measure(runs: Path, window: int) -> dict:
    listings = with_reads = reads_after = locating = 0
    per_listing = Counter()
    sessions = 0
    for stream in sorted(runs.glob("*/stream.jsonl")):
        sessions += 1
        ev = list(events(stream))
        for i, (kind, where, _) in enumerate(ev):
            if kind != "list":
                continue
            listings += 1
            nxt = ev[i + 1:i + 1 + window]
            hits = [(j, e) for j, e in enumerate(nxt) if e[0] == "read" and (e[1] + "/").startswith(where.rstrip("/") + "/" if where != "." else "")]
            per_listing[min(len(hits), 3)] += 1
            if hits:
                with_reads += 1
            reads_after += len(hits)
            for j, _ in hits:
                if any(e[0] == "defgrep" for e in nxt[:j]):
                    locating += 1
    return {"sessions": sessions, "window": window, "listings": listings, "listings_followed_by_a_read": with_reads,
            "reads_after_listings": reads_after, "of_which_locating_a_symbol": locating,
            "listings_by_reads_after": {("3+" if k == 3 else str(k)): v for k, v in sorted(per_listing.items())}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs")
    ap.add_argument("--window", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = measure(Path(a.runs), a.window)
    if a.json:
        print(json.dumps(r))
        return 0
    n = r["listings"] or 1
    print(f"{r['sessions']} sessions, {r['listings']} folder listings; window {r['window']} calls")
    print(f"  followed by at least one read in that folder: {r['listings_followed_by_a_read']} ({100 * r['listings_followed_by_a_read'] / n:.0f}%)")
    print(f"  reads in the folder after a listing: {r['reads_after_listings']} ({r['reads_after_listings'] / n:.2f} per listing),"
          f" of which after a definition grep: {r['of_which_locating_a_symbol']}")
    print(f"  listings by reads after: {r['listings_by_reads_after']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
