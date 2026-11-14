"""Component + Subsystem containment (devkb BL-8, KNOWLEDGE_SPEC.md Section
4/5).

Per `12-sys-arch.pdf` (Cornell CS5150): a Component is the *implementation
of* a Subsystem, not a level above it -- Section 2's audit corrected an
earlier inverted framing. Both sides are real, already-existing data, zero
new hand-curated grouping:
  - Component mirrors `discovery/`'s own already-built `Service` nodes
    (`.onboarding/graph.json`) -- same natural_key, so the two stores stay
    joinable without a lookup table.
  - Subsystem is `pms.config.json`'s own real `subsystems` list.
  - PART_OF (File -> Component): from each Module's own `service` property,
    already computed by discovery, promoted to a real edge.
  - REALIZES (Component -> Subsystem): a deterministic path-prefix match,
    longest match wins when a Component's path falls under more than one
    subsystem path candidate (skip, don't guess, when none match).

Needs no ticket, no commit history, no build_symbols.py output -- purely a
function of `.onboarding/graph.json` (if a discovery scan has been run for
this project) and `pms.config.json` (always present, `project_context.py`
already refuses to resolve a project without one). Missing
`.onboarding/graph.json` yields an empty graph, not an error -- same
"can't check yet" framing used everywhere else in devkb for an optional
upstream input.
"""
from __future__ import annotations

import json
from pathlib import Path

from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext, load_config


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _subsystem_for(component_path: str, subsystems: list[dict]) -> dict | None:
    """Longest-prefix match: component_path == subsystem path, or nested
    one directory level or more under it. None when no subsystem's path is
    a real prefix -- skipped, not guessed."""
    best: dict | None = None
    for s in subsystems:
        sp = s.get("path", "").strip("/")
        if not sp:
            continue
        if component_path == sp or component_path.startswith(f"{sp}/"):
            if best is None or len(sp) > len(best.get("path", "").strip("/")):
                best = s
    return best


def extract(ctx: ProjectContext) -> DevKBGraph:
    g = DevKBGraph()

    graph_path = ctx.repo_root / ".onboarding" / "graph.json"
    discovery = _read_json(graph_path)
    if discovery is None:
        return g

    nodes = discovery.get("nodes", [])
    services = {n["natural_key"]: n for n in nodes if n.get("type") == "Service"}
    modules = [n for n in nodes if n.get("type") == "Module"]
    if not services:
        return g

    cfg = load_config(ctx.repo_root)
    subsystems = cfg.get("subsystems", [])

    # Component nodes + REALIZES -- one per real discovery Service, path
    # relative to the repo root (needed both for REALIZES' own prefix
    # match and as the Component's own queryable `path` property).
    component_paths: dict[str, str] = {}
    for natural_key, svc in services.items():
        root = svc.get("root")
        if not root:
            continue
        try:
            rel_path = str(Path(root).resolve().relative_to(ctx.repo_root)).replace("\\", "/")
        except ValueError:
            continue  # a Service root outside this repo -- not this project's own component
        component_paths[natural_key] = rel_path
        g.add_node("Component", natural_key, source="discovery-service", label=natural_key, path=rel_path)

        match = _subsystem_for(rel_path, subsystems)
        if match:
            g.add_node("Subsystem", match["key"], source="pms.config.json",
                       label=match.get("label", match["key"]), path=match.get("path", ""))
            g.add_edge(
                "REALIZES", "Component", natural_key, "Subsystem", match["key"],
                source="path-prefix-match", confidence=1.0,
                evidence_ref=f"{rel_path} under subsystem path {match.get('path')}",
            )

    # PART_OF (File -> Component) -- from each Module's own `service` +
    # `file` (service-root-relative), promoted to a real edge against a
    # repo-relative File natural_key devkb's own File nodes already use.
    for mod in modules:
        service_name = mod.get("service")
        mod_file = mod.get("file")
        component_path = component_paths.get(service_name)
        if not service_name or not mod_file or component_path is None:
            continue
        file_path = f"{component_path}/{mod_file}" if component_path else mod_file
        g.add_node("File", file_path, source="discovery-module")
        g.add_edge(
            "PART_OF", "File", file_path, "Component", service_name,
            source="discovery-module", confidence=1.0,
            evidence_ref=f"Module {mod.get('natural_key')} (service={service_name})",
        )

    return g
