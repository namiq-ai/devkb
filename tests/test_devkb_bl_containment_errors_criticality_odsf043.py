"""Tests for ODSF-043: devkb BL-8/BL-9/BL-10/BL-14 -- Component+Subsystem
containment, RAISES/LOGS/ErrorSignature, REGISTERED_ON middleware,
Symbol.security_signals (body/legs model, devkb/KNOWLEDGE_SPEC.md).

Covers:
  1. devkb.extractors.component_subsystem (BL-8) -- Component mirrors a
     real discovery Service, Subsystem mirrors a real pms.config.json
     entry, REALIZES path-prefix-matches them, PART_OF derives from a
     Module's own service property.
  2. devkb.build_symbols (BL-9) -- RAISES (incl. the HTTPException
     status_code special case), LOGS, File.description (module docstring),
     Symbol.complexity.
  3. devkb.build_symbols (BL-10) -- REGISTERED_ON resolves a middleware
     argument to a real Symbol, including the cross-file/per-service-root
     import case (`from app.middleware.auth import AuthMiddleware` inside
     a service subdirectory) that a same-repo-root-only resolver misses --
     confirmed live against OCO's own real webapp/backend/app/main.py.
  4. devkb.build_symbols (BL-14) -- security_signals is fully automated:
     path-keyword, registered-as-middleware, enforces-authz-boundary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols, model  # noqa: E402
from devkb.extractors import component_subsystem  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _make_ctx(repo_root: Path, code: str = "TST") -> ProjectContext:
    return ProjectContext(
        code=code, repo_root=repo_root, ticket_prefix=code,
        issues_dir=repo_root / "issues", tests_dir=repo_root / "tests",
        sprint_dir=repo_root / "historical" / "sprints", devkb_dir=repo_root / ".devkb",
        board_file=repo_root / "sdp" / "data" / "PROJECT_BOARD.md",
        wp_map_file=repo_root / "sdp" / "data" / "orchestrator" / "wp-map.json",
    )


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


class TestComponentSubsystem:
    def test_component_mirrors_real_discovery_service(self, tmp_path: Path) -> None:
        (tmp_path / "backend").mkdir()
        onboarding = tmp_path / ".onboarding"
        onboarding.mkdir()
        (onboarding / "graph.json").write_text(json.dumps({
            "nodes": [
                {"type": "Service", "natural_key": "backend", "root": str(tmp_path / "backend")},
                {"type": "Module", "natural_key": "app", "service": "backend", "file": "app.py"},
            ],
        }))
        (tmp_path / "pms.config.json").write_text(json.dumps({"subsystems": []}))
        ctx = _make_ctx(tmp_path)

        g = component_subsystem.extract(ctx)

        components = list(g.nodes("Component"))
        assert len(components) == 1
        assert components[0].natural_key == "backend"
        assert components[0].props["path"] == "backend"

        part_of = list(g.edges("PART_OF"))
        assert len(part_of) == 1
        assert part_of[0].src == "backend/app.py"
        assert part_of[0].dst == "backend"

    def test_realizes_matches_subsystem_by_path_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "webapp" / "backend").mkdir(parents=True)
        onboarding = tmp_path / ".onboarding"
        onboarding.mkdir()
        (onboarding / "graph.json").write_text(json.dumps({
            "nodes": [
                {"type": "Service", "natural_key": "webapp-backend", "root": str(tmp_path / "webapp" / "backend")},
            ],
        }))
        (tmp_path / "pms.config.json").write_text(json.dumps({
            "subsystems": [{"key": "webapp-backend", "label": "Web App Backend", "path": "webapp/backend"}],
        }))
        ctx = _make_ctx(tmp_path)

        g = component_subsystem.extract(ctx)

        subsystems = list(g.nodes("Subsystem"))
        assert len(subsystems) == 1
        assert subsystems[0].natural_key == "webapp-backend"

        realizes = list(g.edges("REALIZES"))
        assert len(realizes) == 1
        assert realizes[0].src == "webapp-backend"
        assert realizes[0].dst == "webapp-backend"

    def test_no_matching_subsystem_yields_no_realizes_edge(self, tmp_path: Path) -> None:
        (tmp_path / "orphan").mkdir()
        onboarding = tmp_path / ".onboarding"
        onboarding.mkdir()
        (onboarding / "graph.json").write_text(json.dumps({
            "nodes": [{"type": "Service", "natural_key": "orphan", "root": str(tmp_path / "orphan")}],
        }))
        (tmp_path / "pms.config.json").write_text(json.dumps({
            "subsystems": [{"key": "elsewhere", "label": "Elsewhere", "path": "elsewhere"}],
        }))
        ctx = _make_ctx(tmp_path)

        g = component_subsystem.extract(ctx)

        assert list(g.nodes("Component")) != []
        assert list(g.edges("REALIZES")) == []

    def test_missing_onboarding_graph_yields_empty(self, tmp_path: Path) -> None:
        (tmp_path / "pms.config.json").write_text(json.dumps({"subsystems": []}))
        ctx = _make_ctx(tmp_path)
        g = component_subsystem.extract(ctx)
        assert g.node_count() == 0


class TestRaisesLogsErrorSignature:
    def test_raise_creates_error_signature(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def handler():\n    raise ValueError(\"bad input\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        raises = list(g.edges("RAISES"))
        assert len(raises) == 1
        assert raises[0].src == "app.py::handler"
        sigs = list(g.nodes("ErrorSignature"))
        assert len(sigs) == 1
        assert sigs[0].props["kind"] == "raised"
        assert sigs[0].props["label"] == "ValueError"
        assert sigs[0].props["message_template"] == "bad input"
        # add_node() strips None-valued props -- "status_code" absent
        # entirely means "not applicable", same idiom used everywhere else.
        assert sigs[0].props.get("status_code") is None

    def test_http_exception_literal_status_code_extracted(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def handler():\n    raise HTTPException(status_code=404, detail=\"not found\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        sigs = list(g.nodes("ErrorSignature"))
        assert len(sigs) == 1
        assert sigs[0].props["label"] == "HTTPException"
        assert sigs[0].props["status_code"] == 404
        assert sigs[0].props["message_template"] == "not found"
        raises = list(g.edges("RAISES"))
        assert raises[0].confidence == 1.0

    def test_dynamic_status_code_is_skipped_not_guessed(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def handler(code):\n    raise HTTPException(status_code=code, detail=\"x\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        sigs = list(g.nodes("ErrorSignature"))
        assert len(sigs) == 1
        assert sigs[0].props.get("status_code") is None

    def test_logger_error_creates_error_signature(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def handler():\n    logger.error(\"something broke\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)

        logs = list(g.edges("LOGS"))
        assert len(logs) == 1
        sigs = list(g.nodes("ErrorSignature"))
        assert sigs[0].props["kind"] == "logged"
        assert sigs[0].props["label"] == "error"
        assert sigs[0].props["message_template"] == "something broke"

    def test_logger_exception_maps_to_error_level(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def handler():\n    logger.exception(\"boom\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)
        sigs = list(g.nodes("ErrorSignature"))
        assert sigs[0].props["label"] == "error"

    def test_raise_and_log_with_same_message_share_one_error_signature(self, tmp_path: Path) -> None:
        """Different sources (RAISES vs LOGS), same real-world error --
        different `kind` prevents a false merge even with the same text."""
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def a():\n    raise ValueError(\"dup\")\n\n\ndef b():\n    raise ValueError(\"dup\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)
        sigs = list(g.nodes("ErrorSignature"))
        assert len(sigs) == 1  # same kind+label+message -> same node, real dedup
        raises = list(g.edges("RAISES"))
        assert len(raises) == 2
        assert {e.src for e in raises} == {"app.py::a", "app.py::b"}

    def test_file_description_is_module_docstring(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text('"""This module does X."""\ndef f():\n    pass\n')
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)
        files = list(g.nodes("File"))
        assert files[0].props["description"] == "This module does X."

    def test_symbol_complexity_counts_branches(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def f(x):\n"
            "    if x:\n"
            "        pass\n"
            "    for i in range(3):\n"
            "        pass\n"
            "    return x\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)
        sym = next(s for s in g.nodes("Symbol") if s.natural_key == "app.py::f")
        assert sym.props["complexity"] == 2


class TestRegisteredOnAndSecuritySignals:
    def _repo_with_cross_service_middleware(self, tmp_path: Path) -> None:
        (tmp_path / "webapp" / "backend" / "app" / "middleware").mkdir(parents=True)
        (tmp_path / "webapp" / "backend" / "app" / "middleware" / "auth.py").write_text(
            "class AuthMiddleware:\n    pass\n"
        )
        (tmp_path / "webapp" / "backend" / "app" / "main.py").write_text(
            "from app.middleware.auth import AuthMiddleware\n\n"
            "app.add_middleware(AuthMiddleware)\n"
        )
        _init_repo(tmp_path)
        _commit_all(tmp_path)

    def test_registered_on_resolves_cross_service_root_import(self, tmp_path: Path) -> None:
        """The exact real-world case found live in OCO's own
        webapp/backend/app/main.py -- `from app.middleware.auth import
        AuthMiddleware` means webapp/backend/app/middleware/auth.py, not a
        repo-root-level app/, because webapp/backend is its own service
        root. A resolver that only tries the dotted path against the repo
        root misses this entirely."""
        self._repo_with_cross_service_middleware(tmp_path)

        g = build_symbols.extract(tmp_path)

        reg = list(g.edges("REGISTERED_ON"))
        assert len(reg) == 1
        assert reg[0].src == "webapp/backend/app/middleware/auth.py::AuthMiddleware"
        assert reg[0].dst.startswith("* ")

    def test_registered_middleware_symbol_gets_security_signal(self, tmp_path: Path) -> None:
        self._repo_with_cross_service_middleware(tmp_path)
        g = build_symbols.extract(tmp_path)
        sym = next(s for s in g.nodes("Symbol")
                   if s.natural_key == "webapp/backend/app/middleware/auth.py::AuthMiddleware")
        assert "registered-as-middleware" in sym.props["security_signals"]
        assert "path-keyword:auth" in sym.props["security_signals"]

    def test_401_raise_gets_authz_boundary_signal(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def handler():\n    raise HTTPException(status_code=401, detail=\"nope\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)
        sym = next(s for s in g.nodes("Symbol") if s.natural_key == "app.py::handler")
        assert "enforces-authz-boundary" in sym.props["security_signals"]

    def test_500_raise_does_not_get_authz_boundary_signal(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "def handler():\n    raise HTTPException(status_code=500, detail=\"oops\")\n"
        )
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)
        sym = next(s for s in g.nodes("Symbol") if s.natural_key == "app.py::handler")
        assert sym.props.get("security_signals", []) == []

    def test_ordinary_symbol_has_no_security_signals(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "math_utils.py").write_text("def add(a, b):\n    return a + b\n")
        _commit_all(tmp_path)

        g = build_symbols.extract(tmp_path)
        sym = next(s for s in g.nodes("Symbol") if s.natural_key == "math_utils.py::add")
        assert sym.props.get("security_signals", []) == []


def test_new_node_types_and_verbs_are_governed() -> None:
    for t in ("Component", "Subsystem", "ErrorSignature"):
        assert t in model.NODE_TYPES
    for v in ("REALIZES", "RAISES", "LOGS", "REGISTERED_ON"):
        assert v in model.VERBS
