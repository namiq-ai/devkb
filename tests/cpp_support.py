"""Shared helpers for the C/C++ tests (DKB-002..DKB-007): small fixture repositories, built and queried for real.

Fixture code is synthetic. Addresses use RFC5737 (192.0.2.0/24) and MACs RFC7042 (00-00-5E-00-53-xx)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols, process_api  # noqa: E402
from devkb.packs import Packer  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def make_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=root, check=True, capture_output=True)
    return root


def build(root: Path, files: dict[str, str]):
    return build_symbols.extract(make_repo(root, files))


def symbols(g) -> dict[str, object]:
    return {n.natural_key: n for n in g.nodes("Symbol") if n.source == "cpp-symbols"}


def calls(g) -> set[tuple[str, str]]:
    return {(e.src, e.dst) for e in g.edges("CALLS") if e.source.startswith("cpp-")}


def api(root: Path, files: dict[str, str], monkeypatch):
    """Build the full cpp graph into a `.devkb` store and return (ProcessAPI, Packer)."""
    from devkb.extractors import test_inventory

    repo = make_repo(root, files)
    g = build_symbols.extract(repo)
    ctx = ProjectContext(code="TST", repo_root=repo, ticket_prefix="TST", issues_dir=repo / "issues", tests_dir=repo / "tests",
                         sprint_dir=repo / "h", devkb_dir=repo / ".devkb", board_file=repo / "b.md", wp_map_file=repo / "w.json")
    for n in test_inventory.extract(ctx).nodes():
        g.add_node(n.type, n.natural_key, n.source, **n.props)
    for e in test_inventory.extract(ctx).edges():
        g.add_edge(e.verb, e.src_type, e.src, e.dst_type, e.dst, e.source, e.confidence, e.evidence_ref, e.extra)
    store = ctx.devkb_dir
    store.mkdir()
    d = g.to_dict()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-16T00:00:00+00:00", "git_head": head}))
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    a = process_api.ProcessAPI("TST", telemetry=False)
    return a, Packer(a)
