"""Threshold-free ticket similarity (devkb BL-11, KNOWLEDGE_SPEC.md Section
5, resolution of Open question 4).

The original draft gated SIMILAR_TO behind a build-time overlap threshold
("what fraction counts as similar enough to surface") -- dropped per
direct pushback: a guessed constant baked into the graph build is the
wrong place to make that call. This creates the edge for ANY nonzero
touched-file overlap between two tickets' own `REFERENCES`-linked commits'
`TOUCHES`-linked files, and stores the real overlap
(`shared_file_count`/`overlap_score`) as edge data -- filtering ("show me
only the top 3" / "only above 0.3") moves to query time, the same shape
`list_nodes()`'s own `q` search already uses (rank at the edge, don't
gate at the build).

Needs the FULL merged graph (Ticket/Commit/File nodes, REFERENCES/TOUCHES
edges from Phase 1/BL-1, already shipped) -- a post-merge derivation pass,
not a new source, so it runs from `graph` itself like BL-4/BL-6, not as a
`graphs[]` entry in build.py.
"""
from __future__ import annotations

from itertools import combinations
from math import log

from devkb.model import DevKBGraph

#: ODSF-314: neighbours kept per ticket; process_api's index keeps 8, so more is never read.
TOP_NEIGHBOURS = 8
from devkb.project_context import ProjectContext

# A heartbeat/status file touched by nearly every commit regardless of what
# the commit is actually about carries ZERO discriminating signal for "are
# these two tickets related" -- this is a data-quality exclusion (which
# files can even be evidence), not the build-time overlap-score THRESHOLD
# that was explicitly rejected (Section 5's resolution, Open question 4) --
# that rejection was about gating which edges get SHOWN based on a guessed
# significance cutoff; this is about which files get COUNTED at all.
# Confirmed live, not theorized: on OCO's own real history, sdp/orchestrator/
# status/*.md files are touched by 887-946 of 2,614 commits (34-36%) -- CM.md
# alone by 946 -- an extreme structural outlier next to any real functional
# file, already recognized elsewhere in this codebase's own tooling as a
# distinct "status file heartbeat" category (see gate-1's own check of that
# name). Path-based, same discipline as every other allow/exclude-list in
# this spec, extensible if a different project's own hub files show up.
_HUB_FILE_PREFIXES = ("sdp/orchestrator/status/",)

#: A file touched by more than this share of the tickets that touch anything
#: is bookkeeping, not subject matter, and two tickets sharing it are not
#: related in any sense a reader cares about.
#:
#: This is the SAME judgement as the prefix list above — which files may serve
#: as evidence at all — not the build-time overlap threshold Section 5 rejected.
#: That rejection was about gating which edges get SHOWN by a guessed
#: significance cutoff; this is about which files can be evidence, and the
#: prefix list's own comment invited it ("extensible if a different project's
#: own hub files show up"). They showed up, and hand-maintaining the list did
#: not scale: measured on OCO's devkb at 2026-08-07, four files nobody had
#: listed produced 161,894 of the 178,114 single-file SIMILAR_TO edges — 91% —
#: led by `tests/test_oco_ticket_coverage.py`, a test asserting that every
#: ticket has coverage and therefore touched by nearly every ticket's commits.
#: It alone accounted for 46% of the entire relation.
#:
#: 0.10 sits an order of magnitude below the status files the prefix list was
#: written for (34-36% of commits) and above the busiest genuinely functional
#: file measured on the same data.
_HUB_FILE_SHARE = 0.10

#: Below this many tickets the share above is sampling noise, not a property of
#: the repository — on five tickets one of them IS 20%, and on the two-ticket
#: case any shared file at all reads as 100% and the relation empties itself.
#: A statistical exclusion needs a population to be computed over; under it the
#: prefix list still applies and nothing else is disqualified.
_HUB_MIN_TICKETS = 30


def _is_hub_file(path: str) -> bool:
    return any(path.startswith(p) for p in _HUB_FILE_PREFIXES)


def hub_files(touched: dict[str, set[str]], share: float = _HUB_FILE_SHARE) -> dict[str, float]:
    """Files touched by too many tickets to discriminate between any two.

    Returned rather than merely applied so the build can record WHICH files
    were disqualified: an exclusion nobody can see is one nobody can argue
    with, and this one is load-bearing enough to be worth arguing with.
    """
    if len(touched) < _HUB_MIN_TICKETS:
        return {}
    df: dict[str, int] = {}
    for files in touched.values():
        for f in files:
            df[f] = df.get(f, 0) + 1
    total = len(touched)
    return {f: n / total for f, n in df.items() if n / total > share}


def _touched_files(graph: DevKBGraph, ticket_key: str) -> set[str]:
    commits = {e.src for e in graph.edges("REFERENCES") if e.dst == ticket_key}
    if not commits:
        return set()
    return {e.dst for e in graph.edges("TOUCHES") if e.src in commits and not _is_hub_file(e.dst)}


def extract(ctx: ProjectContext, graph: DevKBGraph) -> DevKBGraph:
    g = DevKBGraph()
    tickets = [t.natural_key for t in graph.nodes("Ticket")]
    if len(tickets) < 2:
        return g

    touched = {key: _touched_files(graph, key) for key in tickets}
    touched = {k: v for k, v in touched.items() if v}  # a ticket with no touched files can't overlap

    # Second exclusion pass, computed rather than listed. Runs here and not in
    # `_touched_files` because document frequency is a property of the whole
    # ticket set, which that function cannot see one ticket at a time.
    hubs = hub_files(touched)
    if hubs:
        touched = {k: (v - hubs.keys()) for k, v in touched.items()}
        touched = {k: v for k, v in touched.items() if v}
        print(f"  ticket_similarity: {len(hubs)} hub file(s) excluded as evidence "
              f"(touched by >{_HUB_FILE_SHARE:.0%} of tickets): "
              + ", ".join(f"{f} ({s:.0%})" for f, s in
                          sorted(hubs.items(), key=lambda kv: -kv[1])[:5])
              + ("..." if len(hubs) > 5 else ""))
    if len(touched) < 2:
        return g

    # Inverse document frequency over the surviving files. A file two tickets
    # share is only evidence in proportion to how few OTHER tickets share it;
    # weighting by it makes the hub problem self-limiting rather than dependent
    # on the cutoff above catching every case.
    total_tickets = len(touched)
    doc_freq: dict[str, int] = {}
    for files in touched.values():
        for f in files:
            doc_freq[f] = doc_freq.get(f, 0) + 1

    def _idf(path: str) -> float:
        return log(total_tickets / doc_freq.get(path, 1)) + 1.0

    # Inverted index (file -> tickets that touched it): only ticket pairs
    # sharing at least one real file are ever compared. At real scale
    # (confirmed live: 1,250 real tickets on OCO) most pairs share nothing
    # -- a full O(n^2) pairwise scan is wasted work compared over an index
    # built from the actual touch data.
    file_to_tickets: dict[str, set[str]] = {}
    for ticket, files in touched.items():
        for f in files:
            file_to_tickets.setdefault(f, set()).add(ticket)

    shared_counts: dict[tuple[str, str], int] = {}
    for tickets_sharing_file in file_to_tickets.values():
        if len(tickets_sharing_file) < 2:
            continue
        for a, b in combinations(sorted(tickets_sharing_file), 2):
            shared_counts[(a, b)] = shared_counts.get((a, b), 0) + 1

    scored: dict[tuple[str, str], tuple[int, float, float, list[str]]] = {}
    for (a, b), shared_count in shared_counts.items():
        fa, fb = touched[a], touched[b]
        overlap_score = shared_count / len(fa | fb)
        # Rarest first: the sample a reader sees should lead with the file that
        # actually links these two, not whichever sorts first alphabetically.
        shared = sorted(fa & fb, key=lambda f: (-_idf(f), f))
        weighted = sum(_idf(f) for f in shared) / sum(_idf(f) for f in (fa | fb))
        scored[(a, b)] = (shared_count, overlap_score, weighted, shared)
    # ODSF-314: every pair is still scored, threshold-free, but each ticket keeps only its TOP_NEIGHBOURS best: on OCO
    # the full set was 51 neighbours per ticket (58,914 edges) while every reader used the first 8. The confidence is
    # the weighted score itself, not a constant 1.0 for an inference.
    best: dict[str, list[tuple[float, str]]] = {}
    for (a, b), (_c, _o, weighted, _s) in scored.items():
        best.setdefault(a, []).append((weighted, b))
        best.setdefault(b, []).append((weighted, a))
    keep = {src: {dst for _w, dst in sorted(lst, key=lambda p: (-p[0], p[1]))[:TOP_NEIGHBOURS]} for src, lst in best.items()}
    for (a, b), (shared_count, overlap_score, weighted, shared) in scored.items():
        for src, dst in ((a, b), (b, a)):
            if dst not in keep.get(src, ()):
                continue
            g.add_edge(
                "SIMILAR_TO", "Ticket", src, "Ticket", dst,
                source="file-overlap-inference", confidence=round(weighted, 4),
                evidence_ref=f"{shared_count} shared touched files ({', '.join(shared[:5])}{'...' if shared_count > 5 else ''})",
                extra={
                    "shared_file_count": shared_count,
                    "overlap_score": round(overlap_score, 4),
                    # Ranking key. `overlap_score` stays exactly as it was so
                    # anything reading it keeps working; this is the field a
                    # consumer should sort on, because it knows the difference
                    # between sharing a Makefile and sharing one service.
                    "weighted_score": round(weighted, 4),
                },
            )
    return g
