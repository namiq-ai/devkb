"""Flow + STEP: fully automated touch-point BFS (devkb BL-12,
KNOWLEDGE_SPEC.md Section 4/4a/5, resolution of Open question 3).

The original draft made `Flow` a curated node type (a human or an
LLM-assisted job proposes an ordered chain, a human confirms). Dropped per
direct instruction: fully automated, no human/LLM step, same rigor as
`CALLS`/`DEFINED_IN`. A touch point (Section 4a -- a graph location
entered from OUTSIDE the call graph itself) seeds a mechanical BFS over
real `CALLS`/`CALLS_API` edges; the result is stored, not curated.

Runs deliberately LAST in the build order: needs BL-7's `Endpoint` nodes
(one touch-point kind) and the full cross-file `CALLS`/`CALLS_API` graph
already merged, or a BFS over an incomplete call graph would produce
truncated/wrong flows. Post-merge, same shape as BL-4/BL-6/BL-11.
"""
from __future__ import annotations

from collections import deque

from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

# Allow-list, extensible -- same discipline as every other allow-list in
# this codebase (_HTTP_METHODS, the logger-level list, etc.).
_SCHEDULER_DECORATOR_PATTERNS = ("celery_app.task", "shared_task", "scheduler.scheduled_job")
_MAX_BFS_DEPTH = 50  # engineering safety valve, not a design choice


def _is_ui_handler_name(short_name: str) -> bool:
    if short_name.startswith("on") and len(short_name) > 2 and short_name[2].isupper():
        return True
    return short_name.startswith("handle") and len(short_name) > 6 and short_name[6].isupper()


def _detect_touch_points(graph: DevKBGraph) -> list[tuple[str, str]]:
    """[(touch_point_kind, start_symbol_natural_key), ...] -- an Endpoint
    touch point resolves immediately to its own owner_symbol here, so
    every touch point downstream is uniformly a Symbol to BFS from."""
    touch_points: list[tuple[str, str]] = []

    for ep in graph.nodes("Endpoint"):
        owner = ep.props.get("owner_symbol")
        if owner:  # excludes BL-10's wildcard middleware markers (method="*", no owner)
            touch_points.append(("endpoint", owner))

    called_targets = {e.dst for e in graph.edges("CALLS")} | {e.dst for e in graph.edges("CALLS_API")}

    for sym in graph.nodes("Symbol"):
        short = sym.natural_key.rsplit("::", 1)[-1].rsplit(".", 1)[-1]

        if (sym.source == "ast-ts" and _is_ui_handler_name(short)
                and sym.natural_key not in called_targets):
            touch_points.append(("ui_handler", sym.natural_key))

        decorators = sym.props.get("decorators") or []
        if any(pat in d for d in decorators for pat in _SCHEDULER_DECORATOR_PATTERNS):
            touch_points.append(("scheduled", sym.natural_key))

        if sym.props.get("is_daemon_entry"):
            touch_points.append(("daemon_entry", sym.natural_key))

    return touch_points


def _bfs(start_symbol: str, adjacency: dict[str, list[tuple[str, float]]]) -> list[tuple[str, int, float]]:
    """[(natural_key, sequence, weakest_link_confidence), ...] in BFS visit
    order, NOT including start_symbol itself (the Flow node's own STEP 0
    already represents the touch point). Cycle-guarded via `visited`,
    depth-capped as a safety valve against runaway/cyclic call graphs."""
    visited = {start_symbol}
    queue: deque[tuple[str, float, int]] = deque([(start_symbol, 1.0, 0)])
    steps: list[tuple[str, int, float]] = []
    seq = 0
    while queue:
        current, path_confidence, depth = queue.popleft()
        if depth >= _MAX_BFS_DEPTH:
            continue
        for neighbor, edge_confidence in adjacency.get(current, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            weakest = min(path_confidence, edge_confidence)
            seq += 1
            steps.append((neighbor, seq, weakest))
            queue.append((neighbor, weakest, depth + 1))
    return steps


def extract(ctx: ProjectContext, graph: DevKBGraph) -> DevKBGraph:
    g = DevKBGraph()
    touch_points = _detect_touch_points(graph)
    if not touch_points:
        return g

    adjacency: dict[str, list[tuple[str, float]]] = {}
    for verb in ("CALLS", "CALLS_API"):
        for e in graph.edges(verb):
            adjacency.setdefault(e.src, []).append((e.dst, e.confidence))

    for kind, start_symbol in touch_points:
        steps = _bfs(start_symbol, adjacency)
        flow_key = f"flow:{kind}:{start_symbol}"
        g.add_node("Flow", flow_key, source="touch-point-bfs", touch_point_kind=kind, step_count=len(steps) + 1)

        g.add_edge(
            "STEP", "Flow", flow_key, "Symbol", start_symbol,
            source="touch-point-bfs", confidence=1.0,
            evidence_ref=f"{kind} touch point", extra={"sequence": 0},
        )
        for target_key, seq, confidence in steps:
            g.add_edge(
                "STEP", "Flow", flow_key, "Symbol", target_key,
                source="touch-point-bfs", confidence=confidence,
                evidence_ref=f"reached from {kind} touch point {start_symbol} via CALLS/CALLS_API",
                extra={"sequence": seq},
            )
    return g
