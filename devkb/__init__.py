"""devkb — cross-project dev-process knowledge graph (ADR-SDP-DEVKB-001).

Tickets, Bug Lineage, git commit log, work packages/milestones (Phase 1);
source files/tests, compliance warnings, specs (later phases). One small,
governed graph per registered project, persisted at
<project-repo>/.devkb/{nodes,edges,manifest}.jsonl — not a fork of OCO's
cyber-threat-intel graph (ADR-SDP-FACTORY-EXTRACTION-001 judged that one
domain-coupled and deliberately non-reusable) and not an extension of
discovery/'s component-architecture graph (discovery/ontology.md scopes
itself to source structure only, by design).
"""
