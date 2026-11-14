"""Module (discovery/graph.json) <-> File (devkb) natural-key translation
(devkb Phase 2 step 2, ADR-SDP-DEVKB-001, ODSF-032).

The two graphs stay independent stores -- different domain, different update
cadence, per the ADR's own rejection of merging them. This is a query-time
join helper only, never a persisted merge.

Translation is exact, not a dotted-module-to-path guess: extract_python.py/
extract_typescript.py already write each Module node's `file` property
relative to its own Service's root, and each Service node's `root` property
is that service's absolute path -- so a Module's path relative to repo_root
is just `service.root.relative_to(repo_root) / module.file`.
"""
from __future__ import annotations

import json
from pathlib import Path


def build_module_to_file(discovery_graph_path: Path, repo_root: Path) -> dict[str, str]:
    """{module_natural_key: file_path_relative_to_repo_root}. A Module whose
    Service has no root under repo_root, or whose graph.json is missing/
    unreadable, is silently skipped -- "can't translate" is a correct answer
    here, not an error worth raising (a discovery graph may not exist yet,
    e.g. before Step 2 of onboard.py has ever run)."""
    try:
        data = json.loads(discovery_graph_path.read_text())
    except (OSError, ValueError):
        return {}

    service_roots: dict[str, Path] = {}
    for n in data.get("nodes", []):
        if n.get("type") == "Service" and n.get("root"):
            service_roots[n["natural_key"]] = Path(n["root"])

    repo_root_resolved = repo_root.resolve()
    out: dict[str, str] = {}
    for n in data.get("nodes", []):
        if n.get("type") != "Module":
            continue
        svc_root = service_roots.get(n.get("service"))
        rel_file = n.get("file")
        if svc_root is None or not rel_file:
            continue
        try:
            svc_rel = svc_root.resolve().relative_to(repo_root_resolved)
        except ValueError:
            continue  # service root isn't under this repo -- can't translate
        out[n["natural_key"]] = str(svc_rel / rel_file)
    return out


def file_to_module(discovery_graph_path: Path, repo_root: Path) -> dict[str, str]:
    """Inverse of build_module_to_file -- the direction devkb's own File
    nodes need at query time: given a devkb File natural_key (a repo-relative
    path), find the richer discovery Module context (service, uid) for it."""
    return {file_path: mod_key for mod_key, file_path in build_module_to_file(discovery_graph_path, repo_root).items()}
