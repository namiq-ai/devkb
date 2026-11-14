"""Commit-cluster inference (devkb BL-6, body/legs model) -- deterministic
clustering only. The LLM narrative step (a plain-language description per
cluster) is flagged as follow-up work requiring an explicit cost go-ahead,
not built here -- a WorkUnit is still real, queryable signal without it
(member commits, span, touched-file count).

For a repo with real commit history and zero real tickets: groups Commit
nodes with no REFERENCES edge to a real Ticket into WorkUnit nodes -- a
first approximation of "this was probably one unit of work." Deliberately
a DIFFERENT node type from Ticket, never merged or presented as
equivalent -- see devkb/ROADMAP.md's own body/legs model / Cross-phase
notes for why that distinction is permanent, not a naming detail.

Clustering signal is day-granularity (git log's own --date=short resolution,
already fetched elsewhere -- no extra subprocess call added just for finer
timestamps) + same author + any touched-file overlap. Confidence is 0.5 on
every GROUPS edge -- lower than any other edge in the graph -- because this
is a labeled guess, not derived fact.
"""
from __future__ import annotations

from devkb.model import DevKBGraph, Node
from devkb.project_context import ProjectContext


def _unreferenced_commits(graph: DevKBGraph) -> list[Node]:
    referenced = {e.src for e in graph.edges("REFERENCES")}
    commits = [c for c in graph.nodes("Commit") if c.natural_key not in referenced]
    return sorted(commits, key=lambda c: c.props.get("date", ""))


def _commit_to_files_index(graph: DevKBGraph) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for e in graph.edges("TOUCHES"):
        index.setdefault(e.src, set()).add(e.dst)
    return index


def _cluster(commits: list[Node], files_by_commit: dict[str, set[str]]) -> list[list[Node]]:
    clusters: list[list[Node]] = []
    current: list[Node] = []
    current_files: set[str] = set()
    for c in commits:
        this_files = files_by_commit.get(c.natural_key, set())
        if not current:
            current, current_files = [c], set(this_files)
            continue
        same_day = current[-1].props.get("date") == c.props.get("date")
        same_author = current[-1].props.get("author") == c.props.get("author")
        overlaps = bool(current_files & this_files) or not current_files or not this_files
        if same_day and same_author and overlaps:
            current.append(c)
            current_files |= this_files
        else:
            clusters.append(current)
            current, current_files = [c], set(this_files)
    if current:
        clusters.append(current)
    return clusters


def extract(ctx: ProjectContext, graph: DevKBGraph) -> DevKBGraph:
    """graph must already contain Commit nodes + REFERENCES edges (Phase 1)
    + TOUCHES edges (BL-1/Phase 2) -- build.py merges these before calling
    this."""
    g = DevKBGraph()
    commits = _unreferenced_commits(graph)
    if not commits:
        return g
    files_by_commit = _commit_to_files_index(graph)

    for idx, cluster in enumerate(_cluster(commits, files_by_commit), start=1):
        first, last = cluster[0], cluster[-1]
        unit_key = f"{first.props.get('date', 'unknown')}-{idx}-{first.natural_key[:10]}"
        touched: set[str] = set()
        for c in cluster:
            touched |= files_by_commit.get(c.natural_key, set())
        g.add_node(
            "WorkUnit", unit_key, source="commit-cluster-inference",
            commit_count=len(cluster), first_date=first.props.get("date"),
            last_date=last.props.get("date"), author=first.props.get("author"),
            touched_file_count=len(touched),
        )
        for c in cluster:
            g.add_edge(
                "GROUPS", "WorkUnit", unit_key, "Commit", c.natural_key,
                source="commit-cluster-inference", confidence=0.5,
                evidence_ref=f"same day + same author + touched-file overlap, cluster {unit_key}",
            )
    return g
