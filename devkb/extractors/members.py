"""A product's graph spans its member repositories (ADR-SDP-DEVKB-005 §1-3, ODSF-312).

A product declares members in its root pms.config.json, `"graph": {"members": [{"code": "LIB", "role": "client"}]}`.
Each member is a registered project with its own graph, built by its own build with its own config; this module
reads that graph and never runs a member's extractors with the product's rules (the ODSF-104 lesson).

  Repository  one per repository, the product's own included; natural key the project code
  IN_REPO     File -> Repository, for every File of the product and of each member
  prefixing   a member node's natural key becomes `<CODE>:<key>`, except ConfigKey (the same setting name in two
              repositories is one setting) and Repository; the product's own keys never change
  CALLS_API   member Symbol -> product route-handler Symbol, when a URL the member's code uses has the path of a
              product Endpoint (confidence 0.6: a path match, the HTTP method is not known statically)
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from devkb.model import DevKBGraph
from devkb.project_context import load_config

SOURCE = "members"
UNPREFIXED = {"ConfigKey", "Repository"}


def declared_members(repo_root: Path) -> list[dict]:
    try:
        cfg = load_config(repo_root)
    except (OSError, ValueError):
        return []
    members = ((cfg.get("graph") or {}).get("members") or []) if isinstance(cfg, dict) else []
    return [m for m in members if isinstance(m, dict) and m.get("code")]


def _load(devkb_dir: Path) -> tuple[list[dict], list[dict]]:
    nodes_p, edges_p = devkb_dir / "nodes.jsonl", devkb_dir / "edges.jsonl"
    if not nodes_p.is_file() or not edges_p.is_file():
        raise ValueError(f"declared member graph not built: {devkb_dir} has no nodes.jsonl/edges.jsonl "
                         f"(build the member first: make devkb-build PROJECT=<CODE>)")
    nodes = [json.loads(l) for l in nodes_p.read_text().splitlines() if l.strip()]
    edges = [json.loads(l) for l in edges_p.read_text().splitlines() if l.strip()]
    return nodes, edges


def _prefixed(code: str, typ: str, key: str) -> str:
    return key if typ in UNPREFIXED else f"{code}:{key}"


# ── URLs a member's code uses ────────────────────────────────────────────────
def _url_paths(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(("http://", "https://")):
            path = urlparse(n.value).path
            if path and path != "/":
                out.append(path.rstrip("/"))
    return out


def url_uses(text: str) -> list[tuple[str, str]]:
    """(qualified function name, URL path) for every URL a function uses, directly or through a module constant."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    constants: dict[str, list[str]] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            paths = _url_paths(stmt.value)
            for t in stmt.targets:
                if isinstance(t, ast.Name) and paths:
                    constants[t.id] = paths
    found: list[tuple[str, str]] = []

    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, stack + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join(stack + [child.name])
                body_paths = set()
                for n in ast.walk(child):
                    if isinstance(n, ast.Name) and n.id in constants:
                        body_paths.update(constants[n.id])
                body_paths.update(_url_paths(child))
                found.extend((qual, p) for p in sorted(body_paths))
                walk(child, stack + [child.name])
    walk(tree, [])
    return found


def _route_matcher(graph: DevKBGraph) -> list[tuple[re.Pattern, str, str]]:
    out = []
    for ep in graph.nodes("Endpoint"):
        path, owner = ep.props.get("path") or ep.natural_key.split(" ", 1)[-1], ep.props.get("owner_symbol")
        if not owner or not path.startswith("/"):
            continue
        rx = re.compile("^" + re.sub(r"\\\{[^}]+\\\}|\\<[^>]+\\>", "[^/]+", re.escape(path.rstrip("/"))) + "$")
        out.append((rx, owner, ep.natural_key))
    return out


def link_repository(graph: DevKBGraph, code: str, role: str = "product", only_prefix: str | None = None) -> None:
    """A Repository node, and IN_REPO from each File of a member (keys prefixed `<CODE>:`). The product's own files
    get no edge (ODSF-314): an unprefixed key already says which repository it is in, and on OCO that was 23,240
    edges repeating it."""
    graph.add_node("Repository", code, source=SOURCE, role=role)
    if only_prefix is None:
        return
    for key in [n.natural_key for n in graph.nodes("File")]:
        if key.startswith(only_prefix):
            graph.add_edge("IN_REPO", "File", key, "Repository", code, source=SOURCE)


def merge_members(ctx, graph: DevKBGraph, resolve) -> list[dict]:
    """Fold every declared member's graph into `graph`. Returns one summary row per member."""
    summary = []
    routes = _route_matcher(graph)
    for m in declared_members(ctx.repo_root):
        code, role = str(m["code"]).upper(), str(m.get("role") or "member")
        mctx = resolve(code)
        nodes, edges = _load(mctx.devkb_dir)
        by_uid: dict[str, tuple[str, str]] = {}
        for n in nodes:
            if n["type"] == "Repository":
                continue
            key = _prefixed(code, n["type"], n["natural_key"])
            by_uid[n["uid"]] = (n["type"], key)
            graph.add_node(n["type"], key, f"{SOURCE}:{code}:{n.get('source', '')}", **(n.get("properties") or {}))
        n_edges = 0
        for e in edges:
            a, b = by_uid.get(e["from_uid"]), by_uid.get(e["to_uid"])
            if a is None or b is None:
                continue
            p = dict(e.get("properties") or {})
            src, conf, ev = p.pop("source", SOURCE), float(p.pop("confidence", 1.0) or 1.0), p.pop("evidence_ref", "")
            graph.add_edge(e["verb"], a[0], a[1], b[0], b[1], f"{SOURCE}:{code}:{src}", conf, ev, p)
            n_edges += 1
        link_repository(graph, code, role=role, only_prefix=f"{code}:")
        calls = 0
        if routes:
            listed = subprocess.run(["git", "ls-files", "--recurse-submodules", "--", "*.py"], cwd=mctx.repo_root,
                                    capture_output=True, text=True, check=False).stdout.split()
            for rel in listed:
                try:
                    uses = url_uses((mctx.repo_root / rel).read_text(errors="replace"))
                except OSError:
                    continue
                for qual, path in uses:
                    for rx, owner, ep in routes:
                        if rx.match(path):
                            graph.add_edge("CALLS_API", "Symbol", f"{code}:{rel}::{qual}", "Symbol", owner, source=SOURCE,
                                           confidence=0.6, evidence_ref=f"{code}:{rel} uses a URL with the path of {ep}")
                            calls += 1
        summary.append({"code": code, "role": role, "nodes": len(by_uid), "edges": n_edges, "calls_api": calls})
    return summary
