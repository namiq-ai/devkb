"""Helpers for the SPEC-DKB-002 tests: build a fixture directory under tests/fixtures as a real repository.

Fixture code is synthetic (RFC5737 addresses, RFC7042 MACs); no absolute local path appears in any fixture."""
from __future__ import annotations

import json
from pathlib import Path

import cpp_support as S

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def files_of(name: str) -> dict[str, str]:
    root = FIXTURES / name
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


def build(tmp_path: Path, name: str, extra: dict[str, str] | None = None):
    """The graph of fixture `name`; `extra` adds or replaces files for one test."""
    return S.build(tmp_path, {**files_of(name), **(extra or {})})


def api(tmp_path: Path, name: str, monkeypatch, extra: dict[str, str] | None = None):
    return S.api(tmp_path, {**files_of(name), **(extra or {})}, monkeypatch)


def node(g, typ: str, key: str):
    return next((n for n in g.nodes(typ) if n.natural_key == key), None)


def props(g, key: str) -> dict:
    n = node(g, "Symbol", key)
    assert n is not None, f"no Symbol {key}: {sorted(x.natural_key for x in g.nodes('Symbol'))[:20]}"
    return n.props


def edges(g, verb: str = "CALLS") -> dict[tuple[str, str], object]:
    return {(e.src, e.dst): e for e in g.edges(verb)}


def graph_dict(g) -> dict:
    return json.loads(json.dumps(g.to_dict(), sort_keys=True))


def make_fixture_repo(tmp_path: Path, name: str, extra: dict[str, str] | None = None) -> Path:
    """The fixture as a committed git repository (for the corpus measure, which reads a checkout)."""
    return S.make_repo(tmp_path, {**files_of(name), **(extra or {})})
