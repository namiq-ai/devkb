"""Node/edge model for the dev-process knowledge graph (ADR-SDP-DEVKB-001).

Deliberately storage-free, mirroring discovery/model.py's own shape (Node/Edge/
graph-container, deterministic uid, JSON-serializable) rather than inventing a
second graph representation for the same kind of problem — but a distinct
"devkb:" uid domain, so a project's .devkb/ store and its .onboarding/graph.json
can never collide or be silently conflated (different hash domain, different
vocabulary, different update cadence).
"""
from __future__ import annotations

import json

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

# Node types (devkb/ontology.md, ADR-SDP-DEVKB-001). Phase 1 + Phase 2
# (File/TestCase, ODSF-032) + Phase 3 (Warning, ODSF-033) + the BL-series
# (Symbol/Release/WorkUnit, body/legs model -- ticket-independent knowledge
# building) + the KNOWLEDGE_SPEC.md batch (Endpoint/Component/Subsystem/
# Flow/ErrorSignature/Spec, BL-7 through BL-14, ODSF-043) + the renovated
# lifecycle (Requirement/Evidence, BL-14, ADR-SDP-DEVKB-002 §1, ODSF-230).
# Epic and Story are deliberately NOT here: they are Ticket nodes carrying
# `ticket_type`, and the names are query aliases (ADR-SDP-DEVKB-002 §2).
NODE_TYPES = (
    "Ticket", "Commit", "WorkPackage", "Milestone", "File", "TestCase", "Warning",
    "Symbol", "Release", "WorkUnit",
    "Endpoint", "Component", "Subsystem", "Flow", "ErrorSignature", "Spec",
    "Requirement",      # one PMS requirement, natural key REQ-NNN (BL-14)
    "Evidence",         # one ev_/of_ evidence record, confidence as recorded (BL-14)
    # ADR-SDP-DEVKB-005 (ODSF-312): a product graph spans member repositories; settings are things.
    "Repository",       # one registered project's repository, natural key its project code
    "ConfigKey",        # one named setting (env var or config-file key); its value is never stored
    # ADR-DEVKB-007: a pull request, natural key PR-<number> (member repositories: <CODE>:PR-<number>).
    "PullRequest",
)

VERBS = (
    "REFERENCES",       # Commit -> Ticket
    "CAUSED_BY",        # Ticket -> Ticket (Bug Lineage)
    "REGRESSION_OF",    # Ticket -> Ticket (Bug Lineage)
    "DUPLICATE_OF",     # Ticket -> Ticket (Bug Lineage)
    "BLOCKS",           # Ticket -> Ticket (Bug Lineage)
    "PART_OF",          # Ticket -> WorkPackage, or File -> Component (BL-8)
    "BELONGS_TO",       # WorkPackage -> Milestone
    "TOUCHES",          # Commit -> File
    "TESTED_BY",        # File -> TestCase, or Symbol -> TestCase (BL-4)
    "FLAGGED_BY",       # File -> Warning
    "DEFINED_IN",       # Symbol -> File
    "CALLS",            # Symbol -> Symbol (same language; Python cross-file, BL-3b)
    "TAGS",             # Release -> Commit
    "GROUPS",            # WorkUnit -> Commit
    "CALLS_API",        # Symbol (frontend, TS) -> Symbol (backend route handler, BL-4b)
    "REALIZES",         # Component -> Subsystem (BL-8)
    "REGISTERED_ON",    # Symbol (middleware) -> Endpoint (BL-10)
    "RAISES",           # Symbol -> ErrorSignature (BL-9)
    "LOGS",             # Symbol -> ErrorSignature (BL-9)
    "SIMILAR_TO",       # Ticket -> Ticket, threshold-free (BL-11)
    "STEP",             # Flow -> Symbol|Endpoint, sequence: int property (BL-12)
    "DOCUMENTS",        # Spec -> Ticket (BL-13)
    # BL-14, ADR-SDP-DEVKB-002 §3 -- all four from extractors/lifecycle.py.
    "CHILD_OF",         # Story (Ticket) -> Epic (Ticket), Trace `Epic` row
    "DERIVED_FROM",     # Ticket -> Requirement, Trace `Requirement` row
    "IMPLEMENTS",       # Ticket -> Spec, Trace `Specification` row
    "EVIDENCED_BY",     # Ticket | Spec -> Evidence, a cited ev_/of_ id
    # ADR-SDP-DEVKB-005 (ODSF-312), extractors/configuration.py and extractors/members.py.
    "IN_REPO",          # File -> Repository
    "READS",            # Symbol | File (module level) -> ConfigKey
    "DECLARES",         # File -> ConfigKey (.env.example, compose environment, systemd Environment=, pms.config.json)
    "DEPLOYS",          # File -> Component (compose service, systemd unit, Dockerfile)
    # ADR-DEVKB-007, extractors/pull_requests.py.
    "MERGES",           # PullRequest -> Commit (git merge/squash subject 0.9, GitHub commit list 1.0)
    "CLOSES",           # PullRequest -> Ticket (GitHub closing references 1.0, commit-message keyword 0.7 unverified)
)


def uid_for(node_type: str, natural_key: str) -> str:
    """Deterministic SHA-256 identity, same rationale as discovery/model.py's
    own uid_for: a node keeps its identity across re-runs, so a diff between
    two builds means something instead of being noise from re-ordered
    iteration. "devkb:" prefix keeps this store's uids out of any other
    graph's namespace (discovery's are "discovery:", OCO's are bare sha256)."""
    digest = hashlib.sha256(f"{node_type}:{natural_key}".encode()).hexdigest()
    return f"devkb:{node_type.lower()}:{digest[:16]}"


@dataclass
class Node:
    type: str
    natural_key: str
    source: str
    props: dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return uid_for(self.type, self.natural_key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "type": self.type,
            "natural_key": self.natural_key,
            "source": self.source,
            "properties": self.props,
        }


@dataclass(frozen=True)
class Edge:
    verb: str
    src: str  # natural key of the source node (same type-scoped key as Node.natural_key)
    src_type: str
    dst: str
    dst_type: str
    source: str
    confidence: float = 1.0
    evidence_ref: str = ""
    # Verb-specific structured data beyond the three fields every edge
    # already has -- e.g. SIMILAR_TO's shared_file_count/overlap_score
    # (BL-11), meant to be sorted/filtered on at query time, not buried in
    # evidence_ref's free text. hash=False/compare=False: two edges with
    # the same (verb, src, dst) are the same edge for dedup purposes
    # regardless of extra content -- callers that need per-pair extras must
    # not add_edge() the same triple twice with different values.
    extra: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    @property
    def from_uid(self) -> str:
        return uid_for(self.src_type, self.src)

    @property
    def to_uid(self) -> str:
        return uid_for(self.dst_type, self.dst)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_uid": self.from_uid,
            "to_uid": self.to_uid,
            "verb": self.verb,
            "properties": {
                "source": self.source,
                "confidence": self.confidence,
                "evidence_ref": self.evidence_ref,
                **self.extra,
            },
        }


class DevKBGraph:
    """An in-memory dev-process graph with by-type/by-verb iteration. No
    index by uid/adjacency here -- that's devkb/index.py's job, built once at
    query time (traverse_graph.py's GraphIndex pattern), not baked into the
    storage-free container itself."""

    def __init__(self) -> None:
        self._nodes: dict[tuple[str, str], Node] = {}
        self._edges: set[Edge] = set()

    def add_node(self, node_type: str, natural_key: str, source: str, **props: Any) -> Node:
        if node_type not in NODE_TYPES:
            raise ValueError(f"unknown node type {node_type!r}, expected one of {NODE_TYPES}")
        key = (node_type, natural_key)
        existing = self._nodes.get(key)
        clean_props = {k: v for k, v in props.items() if v is not None}
        if existing is not None:
            existing.props.update(clean_props)
            return existing
        node = Node(node_type, natural_key, source, clean_props)
        self._nodes[key] = node
        return node

    def add_edge(
        self, verb: str, src_type: str, src: str, dst_type: str, dst: str,
        source: str, confidence: float = 1.0, evidence_ref: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        if verb not in VERBS:
            raise ValueError(f"unknown verb {verb!r}, expected one of {VERBS}")
        self._edges.add(Edge(verb, src, src_type, dst, dst_type, source, confidence, evidence_ref, extra or {}))

    def nodes(self, node_type: str | None = None) -> Iterator[Node]:
        for (t, _key), node in self._nodes.items():
            if node_type is None or t == node_type:
                yield node

    def edges(self, verb: str | None = None) -> Iterator[Edge]:
        for edge in self._edges:
            if verb is None or edge.verb == verb:
                yield edge

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            # every field in the key: two extractors' edges with the same ends (TOUCHES from
            # git and from the baseline) must not come out in set order (ODSF-230 determinism)
            "edges": [e.to_dict() for e in sorted(self._edges, key=lambda e: (
                e.verb, e.src, e.dst, e.src_type, e.dst_type, e.source, e.evidence_ref, e.confidence,
                json.dumps(e.extra, sort_keys=True, default=str)))],
        }

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)


def merge(graphs: Iterable[DevKBGraph]) -> DevKBGraph:
    """Combine N per-extractor graphs into one project-wide graph -- each
    extractor only knows its own source, so cross-source edges (e.g. a
    Commit REFERENCES a Ticket) are only correct once both sides' nodes
    exist, which is why build.py runs extractors before merging, not
    interleaved."""
    out = DevKBGraph()
    for g in graphs:
        for n in g.nodes():
            out.add_node(n.type, n.natural_key, n.source, **n.props)
        for e in g.edges():
            out.add_edge(e.verb, e.src_type, e.src, e.dst_type, e.dst, e.source, e.confidence, e.evidence_ref, e.extra)
    return out
