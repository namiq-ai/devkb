"""Tests for ODSF-043: devkb BL-3b/BL-3c/BL-4b/BL-7 -- cross-file CALLS
resolution, TypeScript/TSX Symbol extraction, cross-language CALLS_API,
Endpoint as a real node (body/legs model, devkb/KNOWLEDGE_SPEC.md).

Covers:
  1. devkb.build_symbols (BL-3b) -- Python CALLS now resolves across files
     via a caller's own import, not just same-file, at a lower confidence
     than the same-file case.
  2. devkb.ts_symbols (BL-3c) -- TypeScript/TSX Symbol extraction, including
     the object-literal-method case (`const api = { x: () => ... }`) --
     confirmed live to be the dominant real shape in both ODSF's own
     pms-web/src/lib/api.ts and OCO's webapp/frontend/src/lib/api.ts, not
     a synthetic edge case.
  3. devkb.build_symbols (BL-4b) -- a frontend Symbol's own get/post/put
     route call resolves to the real backend Symbol handling that route.
  4. devkb.build_symbols (BL-7) -- Endpoint is a real, independently
     queryable node (natural key "METHOD path"), not just a CALLS_API
     resolution intermediate thrown away after use.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols, model, ts_symbols  # noqa: E402


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")


def _commit_all(root: Path, message: str = "wip") -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


class TestCrossFileCalls:
    def test_calls_resolves_via_import_across_files(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "helper.py").write_text("def compute(x):\n    return x + 1\n")
        (tmp_path / "app.py").write_text(
            "from helper import compute\n\n\ndef handler():\n    return compute(1)\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        cross = [e for e in g.edges("CALLS") if e.source == "ast-cross-file-import"]
        assert len(cross) == 1
        assert cross[0].src == "app.py::handler"
        assert cross[0].dst == "helper.py::compute"
        assert cross[0].confidence == 0.7

    def test_same_file_still_takes_precedence_over_cross_file(self, tmp_path: Path) -> None:
        """A local symbol with the same short name as an imported one must
        resolve locally -- same-file is unambiguous real evidence, cross-file
        import resolution is a fallback, not a competing guess."""
        _init_repo(tmp_path)
        (tmp_path / "helper.py").write_text("def compute(x):\n    return x + 1\n")
        (tmp_path / "app.py").write_text(
            "from helper import compute\n\n\n"
            "def compute(y):\n    return y * 2\n\n\n"
            "def handler():\n    return compute(1)\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        calls = [e for e in g.edges("CALLS") if e.src == "app.py::handler"]
        assert len(calls) == 1
        assert calls[0].dst == "app.py::compute"
        assert calls[0].source == "ast-same-file"

    def test_ambiguous_cross_file_import_is_skipped_not_guessed(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "import os\n\n\ndef handler():\n    return os.missing_symbol()\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        assert list(g.edges("CALLS")) == []


class TestTypeScriptSymbols:
    def test_top_level_function_and_arrow_const_detected(self, tmp_path: Path) -> None:
        source = (
            "export function greet(name: string): string {\n"
            "  return `hi ${name}`;\n"
            "}\n\n"
            "export const shout = (msg: string) => {\n"
            "  return msg.toUpperCase();\n"
            "};\n"
        )
        (tmp_path / "util.ts").write_text(source)
        symbols, route_calls = ts_symbols.extract_file(tmp_path / "util.ts", tmp_path)
        names = {s["qualified_name"] for s in symbols}
        assert names == {"greet", "shout"}
        assert route_calls == []

    def test_object_literal_method_is_a_real_symbol(self, tmp_path: Path) -> None:
        """The dominant real shape in both ODSF's and OCO's own frontends --
        confirmed live, not synthetic. Without this, CALLS_API produced zero
        edges on either project's actual code."""
        source = (
            "async function get<T>(path: string): Promise<T> {\n"
            "  return fetch(path).then(r => r.json());\n"
            "}\n\n"
            "export const pmsApi = {\n"
            "  overview: () => get<Overview>(\"/overview\"),\n"
            "  workpackages: () => get<WP[]>(\"/workpackages\"),\n"
            "};\n"
        )
        (tmp_path / "api.ts").write_text(source)
        symbols, route_calls = ts_symbols.extract_file(tmp_path / "api.ts", tmp_path)
        names = {s["qualified_name"] for s in symbols}
        assert "pmsApi.overview" in names
        assert "pmsApi.workpackages" in names
        assert ("pmsApi.overview", "GET", "/overview") in route_calls
        assert ("pmsApi.workpackages", "GET", "/workpackages") in route_calls

    def test_call_inside_undetected_symbol_is_not_attributed(self, tmp_path: Path) -> None:
        """A call in module-level code outside any detected symbol is simply
        absent, not mis-attributed to the wrong one -- precision over
        recall, same discipline as BL-4's own same-file CALLS resolution."""
        source = 'get("/eager-call-at-module-scope");\n'
        (tmp_path / "eager.ts").write_text(source)
        symbols, route_calls = ts_symbols.extract_file(tmp_path / "eager.ts", tmp_path)
        assert symbols == []
        assert route_calls == []


class TestCallsApiAndEndpoint:
    def _build_fullstack_repo(self, tmp_path: Path) -> None:
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "routes.py").write_text(
            "from fastapi import APIRouter\n\n"
            "router = APIRouter(prefix=\"/api/v1\")\n\n\n"
            "@router.get(\"/overview\")\n"
            "def get_overview():\n"
            "    return {}\n"
        )
        (tmp_path / "frontend").mkdir()
        (tmp_path / "frontend" / "api.ts").write_text(
            "async function get<T>(path: string): Promise<T> {\n"
            "  return fetch(path).then(r => r.json());\n"
            "}\n\n"
            "export const api = {\n"
            "  overview: () => get<Overview>(\"/api/v1/overview\"),\n"
            "};\n"
        )
        _init_repo(tmp_path)
        _commit_all(tmp_path)

    def test_endpoint_is_a_real_persisted_node(self, tmp_path: Path) -> None:
        self._build_fullstack_repo(tmp_path)
        g = build_symbols.extract(tmp_path)

        endpoints = list(g.nodes("Endpoint"))
        assert len(endpoints) == 1
        ep = endpoints[0]
        assert ep.natural_key == "GET /api/v1/overview"
        assert ep.props["method"] == "GET"
        assert ep.props["path"] == "/api/v1/overview"
        assert ep.props["owner_symbol"] == "backend/routes.py::get_overview"

    def test_calls_api_resolves_frontend_to_real_backend_symbol(self, tmp_path: Path) -> None:
        self._build_fullstack_repo(tmp_path)
        g = build_symbols.extract(tmp_path)

        capi = list(g.edges("CALLS_API"))
        assert len(capi) == 1
        assert capi[0].src == "frontend/api.ts::api.overview"
        assert capi[0].dst == "backend/routes.py::get_overview"
        assert capi[0].confidence == 0.85

    def test_unmatched_frontend_route_yields_no_calls_api_edge(self, tmp_path: Path) -> None:
        """A frontend call to a path no backend route matches is left
        unresolved, not guessed -- confirmed real behavior against OCO's
        own apiFetch-wrapper pattern this doesn't (yet) parse."""
        (tmp_path / "frontend").mkdir()
        (tmp_path / "frontend" / "api.ts").write_text(
            "async function get<T>(path: string): Promise<T> {\n"
            "  return fetch(path).then(r => r.json());\n"
            "}\n\n"
            "export const api = {\n"
            "  ghost: () => get<X>(\"/no/such/route\"),\n"
            "};\n"
        )
        _init_repo(tmp_path)
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        assert list(g.edges("CALLS_API")) == []
        assert list(g.nodes("Endpoint")) == []


def test_new_node_type_and_verb_are_governed() -> None:
    assert "Endpoint" in model.NODE_TYPES
    assert "CALLS_API" in model.VERBS
