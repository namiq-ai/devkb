"""Load-time index over a project's .devkb/ store.

Mirrors scripts/traverse_graph.py's GraphIndex pattern (build by_uid/out_edges/
in_edges once at load, O(1) lookups from there) rather than GraphService's
per-call O(N) scan (webapp/backend/app/services/graph_service.py:171) --
applying that lesson from the start instead of retrofitting it after a
measured stall, per ADR-SDP-DEVKB-001.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DevKBIndex:
    by_uid: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_type: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    out_edges: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    in_edges: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    by_natural_key: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    def node(self, node_type: str, natural_key: str) -> dict[str, Any] | None:
        return self.by_natural_key.get((node_type, natural_key))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def load(devkb_dir: Path) -> DevKBIndex:
    idx = DevKBIndex()
    for node in _read_jsonl(devkb_dir / "nodes.jsonl"):
        idx.by_uid[node["uid"]] = node
        idx.by_type[node["type"]].append(node)
        idx.by_natural_key[(node["type"], node["natural_key"])] = node
    for edge in _read_jsonl(devkb_dir / "edges.jsonl"):
        idx.out_edges[edge["from_uid"]].append(edge)
        idx.in_edges[edge["to_uid"]].append(edge)
    return idx
