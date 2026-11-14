#!/usr/bin/env python3
"""devkb build — run every extractor for one project and persist the graph.

Usage: python3 devkb/build.py --project CODE

Writes <project-repo>/.devkb/{nodes.jsonl, edges.jsonl, manifest.json}. Never
hand-edit anything under .devkb/ -- it is regenerated wholesale on every run
(ADR-SDP-TICKETS-001's "generated, disposable index" discipline), so a stale
run is a rebuild away, never a silent-wrong-answer risk if manifest.json's
staleness fields are checked by the caller.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb import build_symbols
from devkb.extractors import (
    backlog, component_subsystem, configuration, files_tests, flows, lifecycle, members, releases, source_baseline,
    spec_docs, symbol_tests,
    test_inventory, ticket_similarity, tickets_git, warnings, work_units,
)
from devkb.gitutil import git_head
from devkb.model import DevKBGraph, merge
from devkb.project_context import resolve


#: This checkout — the one whose extractor code is about to run. Distinct from
#: the target repo, which comes from projects.json.
BUILDER_ROOT = Path(__file__).resolve().parent.parent


def _roots(path: Path) -> set[str]:
    import subprocess  # noqa: PLC0415
    try:
        out = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=path, capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(out.split())


def check_builder_matches_target(repo_root: Path, builder_root: Path = BUILDER_ROOT) -> str | None:
    """The refusal message when this checkout's code would write another
    checkout's graph, or None when the two agree.

    ODSF-104. `--project CODE` takes the TARGET from projects.json and the CODE
    from wherever this file happens to live, and those are not required to be
    the same directory. Run a build inside a git worktree and it rebuilds the
    main checkout's graph using the worktree's extractors and the worktree's
    config -- silently. It happened twice in one day: once during the ODSF-102
    landing, and again at 2026-08-16T01:00, when a build from a pre-ODSF-102
    checkout overwrote a correct 5-document spec index with a 2-document one.

    What makes it hard to catch is that the result looks healthy. The manifest
    records the TARGET's HEAD, so a graph built by stale code carries a current
    commit hash, a recent timestamp and a plausible node count; the only symptom
    is a BA quietly measuring a requirement against two specification documents
    instead of five. A wrong answer wearing a correct label is worse than a
    missing one, so the default is to refuse.
    """
    if repo_root.resolve() == builder_root.resolve():
        return None
    # Installed on its own, devkb's code is never a checkout of the project it analyses, so there is no stale
    # copy of the project's own extractors to fear. The guard applies only when the builder is another checkout
    # (a worktree, a second clone) of the same repository: the two share a root commit.
    if not (_roots(repo_root) & _roots(builder_root)):
        return None
    return (
        f"this checkout is not the project being built.\n"
        f"    extractor code: {builder_root}\n"
        f"    target repo:    {repo_root}\n"
        f"  Building would overwrite the target's graph using THIS checkout's code and\n"
        f"  config, which is how a stale index silently replaces a correct one\n"
        f"  (ODSF-104). Run it from {repo_root}, or pass --allow-foreign-checkout if\n"
        f"  that is genuinely what you want."
    )


def manifest_payload(
    code: str, repo_root: Path, node_count: int, edge_count: int,
) -> dict[str, object]:
    """What `.devkb/manifest.json` records about this build.

    ODSF-104 added the two `builder_*` fields. `git_head` is the TARGET's, and
    is the same hash whichever checkout's extractors produced the graph — which
    is exactly why a stale build looked current. These say which code ran, so a
    stale graph is identifiable by reading the manifest rather than by noticing
    that a BA answer came out oddly thin.

    Its own function so the shape can be asserted without building a graph, and
    without a test depending on whether someone has rebuilt recently.
    """
    return {
        "project": code,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head(repo_root),
        "builder_root": str(BUILDER_ROOT),
        "builder_git_head": git_head(BUILDER_ROOT),
        "node_count": node_count,
        "edge_count": edge_count,
    }


def build(code: str, allow_foreign_checkout: bool = False) -> tuple[DevKBGraph, Path]:
    ctx = resolve(code)
    mismatch = check_builder_matches_target(ctx.repo_root)
    if mismatch and not allow_foreign_checkout:
        raise ValueError(mismatch)
    if mismatch:
        print(f"devkb build: WARNING — running {BUILDER_ROOT}'s extractors against "
              f"{ctx.repo_root} (--allow-foreign-checkout)", file=sys.stderr)
    tickets_graph = tickets_git.extract(ctx)
    # BL-1: ticket-agnostic, needs only ctx -- runs independently of
    # tickets_git, but BEFORE files_tests so its own TOUCHES data can be
    # reused instead of re-paying git diff-tree for the same commits twice.
    baseline_graph = source_baseline.extract(ctx)
    precomputed_touches: dict[str, list[str]] = {}
    for e in baseline_graph.edges("TOUCHES"):
        precomputed_touches.setdefault(e.src, []).append(e.dst)

    # files_tests needs tickets_graph's Commit/Ticket/REFERENCES to derive
    # which commits/tickets to walk -- must run after tickets_git, not
    # interleaved (same ordering rule as merge()'s own docstring).
    graphs = [
        tickets_graph,
        baseline_graph,
        files_tests.extract(ctx, tickets_graph, precomputed_touches=precomputed_touches),
        # ODSF-304: a TestCase for every test function, ticket-marked or not.
        test_inventory.extract(ctx),
        backlog.extract(ctx),
        warnings.extract(ctx),
        releases.extract(ctx),
        # BL-8: Component/Subsystem/PART_OF/REALIZES -- needs only ctx
        # (.onboarding/graph.json + pms.config.json), independent of every
        # other extractor here.
        component_subsystem.extract(ctx),
        # ADR-SDP-DEVKB-005 (ODSF-312): ConfigKey/READS/DECLARES and compose/systemd/Dockerfile Components.
        configuration.extract(ctx),
        # BL-3's Symbol graph is a standalone, separately-refreshed artifact
        # (devkb/build_symbols.py, its own manifest) -- this reads whatever
        # was last written there, never regenerates it. Empty if no refresh
        # has run yet, not an error. Carries BL-7/9/10/14 (Endpoint/RAISES/
        # LOGS/REGISTERED_ON/security_signals) along with it, same cache.
        build_symbols.load_cache(ctx),
    ]
    graph = merge(graphs)

    # BL-4/BL-6/BL-11/BL-13 need the FULL merged graph (Symbol/Endpoint
    # nodes from the cache just merged in; Commit/Ticket/REFERENCES/TOUCHES
    # from every extractor above) -- can't run as graphs[] entries, they
    # read `graph` itself. BL-12 (Flow+STEP) runs LAST and deliberately
    # separate from this tuple: it needs the CALLS/CALLS_API graph fully
    # settled, including nothing from BL-11/BL-13 (unrelated) but ordered
    # last anyway per KNOWLEDGE_SPEC.md's own build-order rule.
    for g in (
        symbol_tests.extract(ctx, graph), work_units.extract(ctx, graph),
        ticket_similarity.extract(ctx, graph), spec_docs.extract(ctx, graph),
    ):
        for n in g.nodes():
            graph.add_node(n.type, n.natural_key, n.source, **n.props)
        for e in g.edges():
            graph.add_edge(e.verb, e.src_type, e.src, e.dst_type, e.dst, e.source, e.confidence, e.evidence_ref, e.extra)

    # BL-14 (ADR-SDP-DEVKB-002, ODSF-230): Requirement/Evidence + CHILD_OF/
    # DERIVED_FROM/IMPLEMENTS/EVIDENCED_BY. Its own pass, AFTER the tuple
    # above: IMPLEMENTS resolves a Trace row against spec_docs' Spec nodes and
    # EVIDENCED_BY scans those Spec files, so spec_docs must already be merged.
    lifecycle_graph = lifecycle.extract(ctx, graph)
    for n in lifecycle_graph.nodes():
        graph.add_node(n.type, n.natural_key, n.source, **n.props)
    for e in lifecycle_graph.edges():
        graph.add_edge(e.verb, e.src_type, e.src, e.dst_type, e.dst, e.source, e.confidence, e.evidence_ref, e.extra)

    flows_graph = flows.extract(ctx, graph)
    for n in flows_graph.nodes():
        graph.add_node(n.type, n.natural_key, n.source, **n.props)
    for e in flows_graph.edges():
        graph.add_edge(e.verb, e.src_type, e.src, e.dst_type, e.dst, e.source, e.confidence, e.evidence_ref, e.extra)

    # ADR-SDP-DEVKB-005 (ODSF-312): fold in each declared member repository's own graph, then link every File to its
    # Repository. After flows, so a member's code is never walked as if the product called it.
    for row in members.merge_members(ctx, graph, resolve):
        print(f"devkb build: member {row['code']} ({row['role']}): {row['nodes']} nodes, {row['edges']} edges, "
              f"{row['calls_api']} CALLS_API into {code}", file=sys.stderr)
    members.link_repository(graph, code)
    configuration.settle(graph)

    # Lifecycle needs the FULL merged graph's own Warning nodes (not one
    # extractor's partial view) and has its own history-file side effect,
    # so it runs once, after merge, not as a graphs[] entry.
    warnings.apply_lifecycle(ctx, graph)

    ctx.devkb_dir.mkdir(parents=True, exist_ok=True)
    data = graph.to_dict()

    nodes_path = ctx.devkb_dir / "nodes.jsonl"
    edges_path = ctx.devkb_dir / "edges.jsonl"
    manifest_path = ctx.devkb_dir / "manifest.json"

    nodes_path.write_text("\n".join(json.dumps(n) for n in data["nodes"]) + ("\n" if data["nodes"] else ""))
    edges_path.write_text("\n".join(json.dumps(e) for e in data["edges"]) + ("\n" if data["edges"] else ""))
    manifest_path.write_text(json.dumps(
        manifest_payload(ctx.code, ctx.repo_root, graph.node_count(), graph.edge_count()),
        indent=2,
    ))

    return graph, ctx.devkb_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the devkb graph for one project")
    ap.add_argument("--project", required=True, help="Project code, e.g. ODSF (see projects.json)")
    ap.add_argument(
        "--allow-foreign-checkout", action="store_true",
        help="build a project whose repo is not this checkout (ODSF-104: refused by "
             "default, because a build from a worktree silently overwrites the main "
             "graph with that worktree's code)",
    )
    args = ap.parse_args()

    try:
        graph, devkb_dir = build(args.project, allow_foreign_checkout=args.allow_foreign_checkout)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"devkb build ({args.project}): {graph.node_count()} nodes, {graph.edge_count()} edges "
          f"-> {devkb_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
