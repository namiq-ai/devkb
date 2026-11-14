"""Ticket-agnostic Commit/File baseline extractor (devkb BL-1, body/legs model).

Phase 1's tickets_git.py only ever finds a commit via `git log --grep=<ticket>`
-- per ticket. A repo with real commits and zero tickets filed in this
project's own convention (one project: real source, real commits, real markdown
design docs, no tickets) gets nothing from that path, by construction, not
by bug -- devkb/ROADMAP.md's own "body/legs model" section works through why.

This extractor walks git history directly, independent of any ticket, and is
purely additive: DevKBGraph.add_node()/add_edge() dedupe by natural key, so a
commit found by both this and tickets_git.py's own ticket-mediated walk just
merges into one node, no conflict, no double-counting.

Bounded by --since, not unbounded `--all` -- OCO's own ticket-mediated walk
already costs ~2m10s at 2,584 commits; an unbounded walk over the same
history needs the same scale discipline.
"""
from __future__ import annotations

from pathlib import Path

from devkb.extractors.files_tests import _files_touched, is_bulk
from devkb.extractors.tickets_git import _run
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

# Wide enough to capture a project's real history without being truly
# unbounded -- every registered project's real age today fits well within
# this, while a pathological decades-old import still gets bounded.
DEFAULT_SINCE = "3 years ago"


def _all_commits(repo_root: Path, since: str) -> list[dict[str, str]]:
    out = _run(
        ["git", "log", "--all", f"--since={since}", "--format=%H|%ad|%an|%s", "--date=short"],
        repo_root,
    )
    commits = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return commits


def extract(ctx: ProjectContext, since: str = DEFAULT_SINCE) -> DevKBGraph:
    g = DevKBGraph()
    for c in _all_commits(ctx.repo_root, since):
        g.add_node(
            "Commit", c["hash"], source="git-log-baseline",
            short_hash=c["hash"][:10], date=c["date"], author=c["author"], subject=c["subject"],
        )
        touched = _files_touched(c["hash"], ctx.repo_root)
        if is_bulk(touched):  # ODSF-314: a bulk change keeps its size, not one edge per file
            g.add_node("Commit", c["hash"], source="git-log-baseline", files_changed=len(touched), bulk=True)
            continue
        for path in touched:
            g.add_node("File", path, source="git-log-baseline")
            g.add_edge(
                "TOUCHES", "Commit", c["hash"], "File", path,
                source="git-log-baseline", confidence=1.0,
                evidence_ref=f"git diff-tree --name-only {c['hash'][:10]}",
            )
    return g
