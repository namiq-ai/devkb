"""Tests for ODSF-043: devkb BL-11/BL-12/BL-13 -- threshold-free ticket
similarity, fully-automated Flow+STEP, Spec+DOCUMENTS (body/legs model,
devkb/KNOWLEDGE_SPEC.md).

Covers:
  1. devkb.extractors.ticket_similarity (BL-11) -- any nonzero touched-file
     overlap between two tickets creates a real SIMILAR_TO edge carrying
     shared_file_count/overlap_score, no build-time threshold.
  2. devkb.model's new Edge.extra (needed by BL-11's shared_file_count/
     overlap_score, which don't fit the existing source/confidence/
     evidence_ref fields) -- round-trips through to_dict()/merge().
  3. devkb.extractors.flows (BL-12) -- touch-point detection (endpoint/
     ui_handler/scheduled/daemon_entry) and the BFS itself: sequence
     numbers, weakest-link confidence, cycle safety.
  4. devkb.extractors.spec_docs (BL-13) -- Spec nodes from real files,
     DOCUMENTS only to a Ticket confirmed to exist in the graph (a stale/
     typo'd mention is skipped, not guessed into a dangling edge).
"""
from __future__ import annotations

from pathlib import Path

import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb.extractors import flows, spec_docs, ticket_similarity  # noqa: E402
from devkb.model import DevKBGraph  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _make_ctx(repo_root: Path, code: str = "TST") -> ProjectContext:
    return ProjectContext(
        code=code, repo_root=repo_root, ticket_prefix=code,
        issues_dir=repo_root / "issues", tests_dir=repo_root / "tests",
        sprint_dir=repo_root / "historical" / "sprints", devkb_dir=repo_root / ".devkb",
        board_file=repo_root / "sdp" / "data" / "PROJECT_BOARD.md",
        wp_map_file=repo_root / "sdp" / "data" / "orchestrator" / "wp-map.json",
    )


class TestTicketSimilarity:
    def _graph_with_two_tickets(self, shared: int, only_a: int, only_b: int) -> DevKBGraph:
        g = DevKBGraph()
        g.add_node("Ticket", "TST-1", source="tickets")
        g.add_node("Ticket", "TST-2", source="tickets")
        g.add_node("Commit", "a" * 40, source="tickets")
        g.add_node("Commit", "b" * 40, source="tickets")
        g.add_edge("REFERENCES", "Commit", "a" * 40, "Ticket", "TST-1", source="tickets")
        g.add_edge("REFERENCES", "Commit", "b" * 40, "Ticket", "TST-2", source="tickets")
        for i in range(shared):
            f = f"shared{i}.py"
            g.add_node("File", f, source="tickets")
            g.add_edge("TOUCHES", "Commit", "a" * 40, "File", f, source="tickets")
            g.add_edge("TOUCHES", "Commit", "b" * 40, "File", f, source="tickets")
        for i in range(only_a):
            f = f"only_a{i}.py"
            g.add_node("File", f, source="tickets")
            g.add_edge("TOUCHES", "Commit", "a" * 40, "File", f, source="tickets")
        for i in range(only_b):
            f = f"only_b{i}.py"
            g.add_node("File", f, source="tickets")
            g.add_edge("TOUCHES", "Commit", "b" * 40, "File", f, source="tickets")
        return g

    def test_any_nonzero_overlap_creates_the_edge_no_threshold(self, tmp_path: Path) -> None:
        graph = self._graph_with_two_tickets(shared=1, only_a=10, only_b=10)
        ctx = _make_ctx(tmp_path)
        g = ticket_similarity.extract(ctx, graph)
        sim = list(g.edges("SIMILAR_TO"))
        assert len(sim) == 2  # both directions
        assert {(e.src, e.dst) for e in sim} == {("TST-1", "TST-2"), ("TST-2", "TST-1")}

    def test_shared_file_count_and_overlap_score_are_real_edge_data(self, tmp_path: Path) -> None:
        graph = self._graph_with_two_tickets(shared=2, only_a=1, only_b=1)
        # union = 2 shared + 1 only_a + 1 only_b = 4; overlap = 2/4 = 0.5
        ctx = _make_ctx(tmp_path)
        g = ticket_similarity.extract(ctx, graph)
        edge = next(e for e in g.edges("SIMILAR_TO") if e.src == "TST-1")
        assert edge.extra["shared_file_count"] == 2
        assert edge.extra["overlap_score"] == 0.5

    def test_zero_overlap_yields_no_edge(self, tmp_path: Path) -> None:
        graph = self._graph_with_two_tickets(shared=0, only_a=3, only_b=3)
        ctx = _make_ctx(tmp_path)
        g = ticket_similarity.extract(ctx, graph)
        assert list(g.edges("SIMILAR_TO")) == []

    def test_extra_round_trips_through_to_dict(self, tmp_path: Path) -> None:
        graph = self._graph_with_two_tickets(shared=1, only_a=0, only_b=0)
        ctx = _make_ctx(tmp_path)
        g = ticket_similarity.extract(ctx, graph)
        data = g.to_dict()
        edge_dict = next(e for e in data["edges"] if e["verb"] == "SIMILAR_TO")
        assert "shared_file_count" in edge_dict["properties"]
        assert "overlap_score" in edge_dict["properties"]

    def test_fewer_than_two_tickets_yields_empty(self, tmp_path: Path) -> None:
        graph = DevKBGraph()
        graph.add_node("Ticket", "TST-1", source="tickets")
        ctx = _make_ctx(tmp_path)
        g = ticket_similarity.extract(ctx, graph)
        assert g.node_count() == 0

    def test_heartbeat_status_files_dont_count_as_overlap(self, tmp_path: Path) -> None:
        """Confirmed live on OCO's real history: sdp/orchestrator/status/
        *.md files are touched by 34-36% of ALL commits regardless of what
        the commit is about -- zero discriminating signal, not real
        evidence of relatedness. Two tickets sharing ONLY a heartbeat file
        must not get a SIMILAR_TO edge."""
        graph = DevKBGraph()
        graph.add_node("Ticket", "TST-1", source="tickets")
        graph.add_node("Ticket", "TST-2", source="tickets")
        graph.add_node("Commit", "a" * 40, source="tickets")
        graph.add_node("Commit", "b" * 40, source="tickets")
        graph.add_edge("REFERENCES", "Commit", "a" * 40, "Ticket", "TST-1", source="tickets")
        graph.add_edge("REFERENCES", "Commit", "b" * 40, "Ticket", "TST-2", source="tickets")
        graph.add_node("File", "sdp/orchestrator/status/DE.md", source="tickets")
        graph.add_edge("TOUCHES", "Commit", "a" * 40, "File", "sdp/orchestrator/status/DE.md", source="tickets")
        graph.add_edge("TOUCHES", "Commit", "b" * 40, "File", "sdp/orchestrator/status/DE.md", source="tickets")

        ctx = _make_ctx(tmp_path)
        g = ticket_similarity.extract(ctx, graph)

        assert list(g.edges("SIMILAR_TO")) == []


class TestHubFilesAreComputedNotListed:
    """The hand-maintained prefix list did not scale, and the shape of the
    failure is worth keeping in front of whoever reads this next.

    Measured on OCO's devkb at 2026-08-07: 206,302 SIMILAR_TO edges over 826
    tickets, a median ticket similar to 270 others. Four files nobody had
    listed produced 91% of the single-file matches — led by
    `tests/test_oco_ticket_coverage.py`, a test asserting every ticket has
    coverage and therefore touched by nearly every ticket's commits, which
    alone accounted for 46% of the entire relation. Replaying this rule over
    that same data removes 84.3% of the pairs and takes the median ticket from
    270 neighbours to 31.
    """

    def _many_tickets(self, n: int, hub: str | None, own: bool = True) -> DevKBGraph:
        g = DevKBGraph()
        for i in range(n):
            ticket, commit = f"TST-{i}", f"{i:040d}"
            g.add_node("Ticket", ticket, source="tickets")
            g.add_node("Commit", commit, source="tickets")
            g.add_edge("REFERENCES", "Commit", commit, "Ticket", ticket, source="tickets")
            if hub:
                g.add_node("File", hub, source="tickets")
                g.add_edge("TOUCHES", "Commit", commit, "File", hub, source="tickets")
            if own:
                mine = f"src/feature_{i}.py"
                g.add_node("File", mine, source="tickets")
                g.add_edge("TOUCHES", "Commit", commit, "File", mine, source="tickets")
        return g

    def test_a_file_touched_by_most_tickets_stops_being_evidence(self, tmp_path: Path) -> None:
        graph = self._many_tickets(40, hub="tests/test_ticket_coverage.py")
        g = ticket_similarity.extract(_make_ctx(tmp_path), graph)
        assert list(g.edges("SIMILAR_TO")) == [], (
            "every ticket touching one file must not make them all similar")

    def test_the_exclusion_is_reported_rather_than_silent(self, tmp_path: Path) -> None:
        """An exclusion nobody can see is one nobody can argue with, and this
        one removes most of the relation."""
        touched = {f"TST-{i}": {"hub.py", f"own{i}.py"} for i in range(40)}
        hubs = ticket_similarity.hub_files(touched)
        assert "hub.py" in hubs
        assert hubs["hub.py"] == 1.0
        assert "own0.py" not in hubs

    def test_a_small_project_is_left_alone(self, tmp_path: Path) -> None:
        """Below the population floor the share is sampling noise — on two
        tickets any shared file reads as 100% and the relation empties
        itself. The prefix list still applies; nothing else is disqualified."""
        touched = {f"TST-{i}": {"shared.py"} for i in range(5)}
        assert ticket_similarity.hub_files(touched) == {}

    def test_a_normal_shared_file_still_creates_the_edge(self, tmp_path: Path) -> None:
        """The threshold-free contract for real overlap is unchanged: this is
        a data-quality exclusion, not the significance cutoff BL-11 rejected."""
        graph = self._many_tickets(40, hub=None)
        shared = "src/service.py"
        graph.add_node("File", shared, source="tickets")
        for i in (0, 1):
            graph.add_edge("TOUCHES", "Commit", f"{i:040d}", "File", shared, source="tickets")
        g = ticket_similarity.extract(_make_ctx(tmp_path), graph)
        assert {(e.src, e.dst) for e in g.edges("SIMILAR_TO")} == {
            ("TST-0", "TST-1"), ("TST-1", "TST-0")}

    def test_sharing_a_rare_file_outranks_sharing_a_common_one(self, tmp_path: Path) -> None:
        """`weighted_score` is the ranking key, and it has to know the
        difference between sharing a Makefile and sharing one service."""
        g = DevKBGraph()
        for i in range(40):
            ticket, commit = f"TST-{i}", f"{i:040d}"
            g.add_node("Ticket", ticket, source="tickets")
            g.add_node("Commit", commit, source="tickets")
            g.add_edge("REFERENCES", "Commit", commit, "Ticket", ticket, source="tickets")
            g.add_node("File", f"own{i}.py", source="tickets")
            g.add_edge("TOUCHES", "Commit", commit, "File", f"own{i}.py", source="tickets")
        # common.py: 3 of 40 tickets — busy enough to be weak evidence, still
        # under the hub cutoff, so it survives to be ranked rather than dropped.
        for i in range(3):
            g.add_node("File", "common.py", source="tickets")
            g.add_edge("TOUCHES", "Commit", f"{i:040d}", "File", "common.py", source="tickets")
        # rare.py: two tickets only.
        for i in (20, 21):
            g.add_node("File", "rare.py", source="tickets")
            g.add_edge("TOUCHES", "Commit", f"{i:040d}", "File", "rare.py", source="tickets")

        out = ticket_similarity.extract(_make_ctx(tmp_path), g)
        rare = next(e for e in out.edges("SIMILAR_TO")
                    if {e.src, e.dst} == {"TST-20", "TST-21"})
        common = next(e for e in out.edges("SIMILAR_TO")
                      if {e.src, e.dst} == {"TST-0", "TST-1"})
        assert rare.extra["overlap_score"] == common.extra["overlap_score"], (
            "fixture check: raw overlap cannot tell these apart — that is the point")
        assert rare.extra["weighted_score"] > common.extra["weighted_score"]


class TestFlows:
    def _graph_with_call_chain(self) -> DevKBGraph:
        g = DevKBGraph()
        g.add_node("Endpoint", "GET /overview", source="ast", method="GET", path="/overview",
                   owner_symbol="app.py::get_overview")
        g.add_node("Symbol", "app.py::get_overview", source="ast", kind="function")
        g.add_node("Symbol", "app.py::compute", source="ast", kind="function")
        g.add_node("Symbol", "app.py::helper", source="ast", kind="function")
        g.add_edge("CALLS", "Symbol", "app.py::get_overview", "Symbol", "app.py::compute",
                   source="ast-same-file", confidence=0.8)
        g.add_edge("CALLS", "Symbol", "app.py::compute", "Symbol", "app.py::helper",
                   source="ast-same-file", confidence=0.7)
        return g

    def test_endpoint_touch_point_produces_a_flow_with_ordered_steps(self, tmp_path: Path) -> None:
        graph = self._graph_with_call_chain()
        ctx = _make_ctx(tmp_path)
        g = flows.extract(ctx, graph)

        flow_nodes = list(g.nodes("Flow"))
        assert len(flow_nodes) == 1
        assert flow_nodes[0].natural_key == "flow:endpoint:app.py::get_overview"
        assert flow_nodes[0].props["step_count"] == 3  # touch point + 2 reached

        steps = sorted(g.edges("STEP"), key=lambda e: e.extra["sequence"])
        assert [e.dst for e in steps] == ["app.py::get_overview", "app.py::compute", "app.py::helper"]
        assert [e.extra["sequence"] for e in steps] == [0, 1, 2]

    def test_step_confidence_is_weakest_link(self, tmp_path: Path) -> None:
        graph = self._graph_with_call_chain()
        ctx = _make_ctx(tmp_path)
        g = flows.extract(ctx, graph)
        steps = {e.dst: e.confidence for e in g.edges("STEP")}
        assert steps["app.py::compute"] == 0.8
        assert steps["app.py::helper"] == 0.7  # min(0.8, 0.7), the weaker second hop

    def test_cyclic_call_graph_does_not_infinite_loop(self, tmp_path: Path) -> None:
        g = DevKBGraph()
        g.add_node("Endpoint", "GET /x", source="ast", method="GET", path="/x", owner_symbol="a.py::a")
        g.add_node("Symbol", "a.py::a", source="ast", kind="function")
        g.add_node("Symbol", "a.py::b", source="ast", kind="function")
        g.add_edge("CALLS", "Symbol", "a.py::a", "Symbol", "a.py::b", source="ast-same-file", confidence=0.8)
        g.add_edge("CALLS", "Symbol", "a.py::b", "Symbol", "a.py::a", source="ast-same-file", confidence=0.8)
        ctx = _make_ctx(tmp_path)
        result = flows.extract(ctx, g)
        steps = list(result.edges("STEP"))
        assert len(steps) == 2  # a (touch point) + b, not an infinite cycle back to a

    def test_wildcard_middleware_endpoint_is_not_a_touch_point(self, tmp_path: Path) -> None:
        g = DevKBGraph()
        g.add_node("Endpoint", "* app.py", source="ast-middleware-wildcard", method="*", path="app.py")
        ctx = _make_ctx(tmp_path)
        result = flows.extract(ctx, g)
        assert list(result.nodes("Flow")) == []

    def test_scheduled_decorator_is_a_touch_point(self, tmp_path: Path) -> None:
        g = DevKBGraph()
        g.add_node("Symbol", "tasks.py::refresh", source="ast", kind="function",
                   decorators=["celery_app.task"])
        ctx = _make_ctx(tmp_path)
        result = flows.extract(ctx, g)
        flow_nodes = list(result.nodes("Flow"))
        assert len(flow_nodes) == 1
        assert flow_nodes[0].props["touch_point_kind"] == "scheduled"

    def test_daemon_entry_is_a_touch_point(self, tmp_path: Path) -> None:
        g = DevKBGraph()
        g.add_node("Symbol", "run.py::main", source="ast", kind="function", is_daemon_entry=True)
        ctx = _make_ctx(tmp_path)
        result = flows.extract(ctx, g)
        flow_nodes = list(result.nodes("Flow"))
        assert len(flow_nodes) == 1
        assert flow_nodes[0].props["touch_point_kind"] == "daemon_entry"

    def test_ui_handler_needs_zero_incoming_calls(self, tmp_path: Path) -> None:
        g = DevKBGraph()
        g.add_node("Symbol", "Form.tsx::handleSubmit", source="ast-ts", kind="function")
        g.add_node("Symbol", "Other.tsx::caller", source="ast-ts", kind="function")
        g.add_edge("CALLS", "Symbol", "Other.tsx::caller", "Symbol", "Form.tsx::handleSubmit",
                   source="ast-same-file", confidence=0.8)
        ctx = _make_ctx(tmp_path)
        result = flows.extract(ctx, g)
        # handleSubmit IS called by something else in the graph -- not a
        # touch point (invoked by graph-visible code, not the DOM/framework)
        assert list(result.nodes("Flow")) == []

    def test_no_touch_points_yields_empty(self, tmp_path: Path) -> None:
        g = DevKBGraph()
        g.add_node("Symbol", "app.py::internal", source="ast", kind="function")
        ctx = _make_ctx(tmp_path)
        result = flows.extract(ctx, g)
        assert result.node_count() == 0


class TestSpecDocs:
    def test_spec_node_created_with_title_and_doc_type(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001.md").write_text("# ADR-001: Do the thing\n\nSome body text.\n")
        ctx = _make_ctx(tmp_path)
        graph = DevKBGraph()

        g = spec_docs.extract(ctx, graph)

        specs = list(g.nodes("Spec"))
        assert len(specs) == 1
        assert specs[0].natural_key == "docs/adr/ADR-001.md"
        assert specs[0].props["title"] == "ADR-001: Do the thing"
        assert specs[0].props["doc_type"] == "adr"

    def test_documents_only_targets_a_real_ticket(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001.md").write_text(
            "# ADR-001\n\n**Related tickets**: TST-5, TST-999 (does not exist)\n"
        )
        ctx = _make_ctx(tmp_path)
        graph = DevKBGraph()
        graph.add_node("Ticket", "TST-5", source="tickets")
        # TST-999 deliberately NOT added -- a stale/typo'd mention.

        g = spec_docs.extract(ctx, graph)

        docs_edges = list(g.edges("DOCUMENTS"))
        assert len(docs_edges) == 1
        assert docs_edges[0].dst == "TST-5"

    def test_no_ticket_mentions_yields_no_documents_edge(self, tmp_path: Path) -> None:
        design_dir = tmp_path / "design"
        design_dir.mkdir()
        (design_dir / "architecture.md").write_text("# Architecture\n\nNo ticket mentions here.\n")
        ctx = _make_ctx(tmp_path)
        graph = DevKBGraph()

        g = spec_docs.extract(ctx, graph)

        specs = list(g.nodes("Spec"))
        assert len(specs) == 1
        assert specs[0].props["doc_type"] == "design"
        assert list(g.edges("DOCUMENTS")) == []
