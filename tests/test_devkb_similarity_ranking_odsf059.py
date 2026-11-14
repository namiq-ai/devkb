"""A context bundle ranks and caps the verbs that fan out (ODSF-059).

`SIMILAR_TO` is threshold-free by design: the extractor emits an edge for ANY
shared touched file and stores the real score, so that filtering can happen
here, at query time -- "rank at the edge, don't gate at the build". The build
half shipped; this half did not, so a bundle carried every neighbour.

What that looked like on OCO's own graph at 2026-08-07: 206,302 SIMILAR_TO
edges over 826 tickets, a median ticket similar to 270 others, the worst to
702. Opening one ticket returned a wall of them and the count nobody wants:
"+673 more edges not shown". That is not a context bundle, it is the backlog.

Two properties, and the second matters as much as the first: the bundle keeps
the strongest links, and it SAYS how many it left out. Silently dropping them
would reintroduce exactly the defect ODSF-058 removed from the report -- a
document that abbreviates without admitting it.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import query  # noqa: E402
from devkb.index import DevKBIndex  # noqa: E402
from devkb.model import DevKBGraph  # noqa: E402


def _index_of(g: DevKBGraph) -> DevKBIndex:
    """Same shape `devkb.index.load()` builds, without going through disk."""
    data = g.to_dict()
    idx = DevKBIndex()
    for node in data["nodes"]:
        idx.by_uid[node["uid"]] = node
        idx.by_type[node["type"]].append(node)
        idx.by_natural_key[(node["type"], node["natural_key"])] = node
    for edge in data["edges"]:
        idx.out_edges[edge["from_uid"]].append(edge)
        idx.in_edges[edge["to_uid"]].append(edge)
    return idx


def _index_with_neighbours(count: int) -> DevKBIndex:
    """One ticket similar to `count` others, each a little weaker than the last."""
    g = DevKBGraph()
    g.add_node("Ticket", "TST-1", source="tickets", title="the one being read")
    for i in range(2, count + 2):
        other = f"TST-{i}"
        g.add_node("Ticket", other, source="tickets", title=f"neighbour {i}")
        score = round(1.0 - i / (count + 10), 4)
        for src, dst in (("TST-1", other), (other, "TST-1")):
            g.add_edge(
                "SIMILAR_TO", "Ticket", src, "Ticket", dst,
                source="file-overlap-inference", confidence=1.0,
                evidence_ref=f"1 shared touched files (src/f{i}.py)",
                extra={"shared_file_count": 1, "overlap_score": 0.01,
                       "weighted_score": score},
            )
    return _index_of(g)


class TestBundleRanksAndCaps:
    def test_a_ticket_with_hundreds_of_neighbours_returns_a_readable_bundle(self) -> None:
        bundle = query.context_bundle(_index_with_neighbours(300), "TST-1")
        kept = [link for link in bundle["outgoing"] if link["verb"] == "SIMILAR_TO"]
        assert len(kept) == query._RANKED_VERBS["SIMILAR_TO"]

    def test_it_keeps_the_strongest_and_says_how_many_it_dropped(self) -> None:
        bundle = query.context_bundle(_index_with_neighbours(300), "TST-1")
        kept = [link for link in bundle["outgoing"] if link["verb"] == "SIMILAR_TO"]
        scores = [link["evidence"]["weighted_score"] for link in kept]
        assert scores == sorted(scores, reverse=True), "kept links must be ranked"
        assert min(scores) > 0.5, "the ten kept must be the ten strongest"
        # 300 out + 300 in, 10 kept each way.
        assert bundle["omitted_by_verb"]["SIMILAR_TO"] == 580
        assert bundle["ranked_by"] == "weighted_score"

    def test_a_small_neighbourhood_is_untouched_and_unannotated(self) -> None:
        bundle = query.context_bundle(_index_with_neighbours(4), "TST-1")
        assert len([e for e in bundle["outgoing"] if e["verb"] == "SIMILAR_TO"]) == 4
        assert "omitted_by_verb" not in bundle, (
            "nothing was dropped, so the bundle must not imply otherwise")

    def test_other_verbs_are_never_capped(self) -> None:
        """Only verbs unbounded by construction are ranked. A ticket with 300
        TOUCHES is reporting a real fact about itself."""
        g = DevKBGraph()
        g.add_node("Ticket", "TST-1", source="tickets")
        g.add_node("Commit", "c" * 40, source="tickets")
        g.add_edge("REFERENCES", "Commit", "c" * 40, "Ticket", "TST-1", source="tickets")
        for i in range(300):
            g.add_node("File", f"src/f{i}.py", source="tickets")
            g.add_edge("TOUCHES", "Commit", "c" * 40, "File", f"src/f{i}.py", source="tickets")
        bundle = query.context_bundle(_index_of(g), "c" * 40)
        assert len([e for e in bundle["outgoing"] if e["verb"] == "TOUCHES"]) == 300
        assert "omitted_by_verb" not in bundle

    def test_a_graph_built_before_weighted_score_still_ranks(self) -> None:
        """`.devkb/` stores are rebuilt, not migrated, so a bundle may be read
        from a store written before the field existed. Falling back keeps the
        cap working instead of ordering arbitrarily."""
        g = DevKBGraph()
        g.add_node("Ticket", "TST-1", source="tickets")
        for i, shared in enumerate(range(2, 32), start=2):
            other = f"TST-{i}"
            g.add_node("Ticket", other, source="tickets")
            for src, dst in (("TST-1", other), (other, "TST-1")):
                g.add_edge(
                    "SIMILAR_TO", "Ticket", src, "Ticket", dst,
                    source="file-overlap-inference", confidence=1.0,
                    evidence_ref="legacy", extra={"overlap_score": shared / 100},
                )
        bundle = query.context_bundle(_index_of(g), "TST-1")
        kept = [e for e in bundle["outgoing"] if e["verb"] == "SIMILAR_TO"]
        scores = [e["evidence"]["overlap_score"] for e in kept]
        assert len(kept) == 10
        assert scores == sorted(scores, reverse=True)
