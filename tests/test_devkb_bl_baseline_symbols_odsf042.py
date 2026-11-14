"""Tests for ODSF-042: devkb BL-1/BL-2/BL-3 -- ticket-agnostic baseline,
release tags, Symbol extraction (body/legs model, devkb/ROADMAP.md).

Covers:
  1. devkb.model -- Symbol/Release/WorkUnit and their edges are governed.
  2. devkb.extractors.source_baseline (BL-1) -- Commit/File/TOUCHES from a
     real git repo with ZERO tickets, the exact case this exists for.
  3. devkb.extractors.releases (BL-2) -- Release/TAGS from a real git tag.
  4. devkb.build_symbols (BL-3) -- Symbol/DEFINED_IN/CALLS AST extraction,
     including a regression guard for a real bug found live: DEFINED_IN's
     own File target must be a real node in the persisted cache, or
     load_cache() has nothing to resolve it against and silently drops
     every such edge on merge.
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
from devkb.extractors import releases, source_baseline  # noqa: E402
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


def test_bl_series_node_types_and_verbs_are_governed() -> None:
    assert "Symbol" in model.NODE_TYPES
    assert "Release" in model.NODE_TYPES
    assert "WorkUnit" in model.NODE_TYPES
    for verb in ("DEFINED_IN", "CALLS", "TAGS", "GROUPS"):
        assert verb in model.VERBS


class TestSourceBaseline:
    def test_zero_tickets_still_yields_commits_and_files(self, tmp_path: Path) -> None:
        """The exact case: real commits, real files, zero tickets --
        tickets_git.py would yield nothing here (no issues/*.md at all), but
        source_baseline.py must yield real signal regardless."""
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text("print('hi')\n")
        _git(tmp_path, "add", "app.py")
        _git(tmp_path, "commit", "-q", "-m", "no ticket mentioned here at all")
        commit_hash = _git(tmp_path, "rev-parse", "HEAD")

        ctx = _make_ctx(tmp_path)
        g = source_baseline.extract(ctx)

        assert [c.natural_key for c in g.nodes("Commit")] == [commit_hash]
        assert [f.natural_key for f in g.nodes("File")] == ["app.py"]
        touches = list(g.edges("TOUCHES"))
        assert len(touches) == 1
        assert touches[0].src == commit_hash and touches[0].dst == "app.py"
        assert touches[0].confidence == 1.0

    def test_since_window_excludes_older_commits(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text("x = 1\n")
        _git(tmp_path, "add", "app.py")
        _git(tmp_path, "commit", "-q", "-m", "first")
        ctx = _make_ctx(tmp_path)
        # A since window that starts in the future excludes every real
        # commit deterministically -- "0 seconds ago" raced against the
        # commit's own timestamp and was flaky.
        g = source_baseline.extract(ctx, since="2099-01-01")
        assert list(g.nodes("Commit")) == []


class TestReleases:
    def test_real_tag_produces_release_and_tags_edge(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text("x = 1\n")
        _git(tmp_path, "add", "app.py")
        _git(tmp_path, "commit", "-q", "-m", "first")
        commit_hash = _git(tmp_path, "rev-parse", "HEAD")
        _git(tmp_path, "tag", "v1.0.0")

        ctx = _make_ctx(tmp_path)
        g = releases.extract(ctx)

        assert [r.natural_key for r in g.nodes("Release")] == ["v1.0.0"]
        tags_edges = list(g.edges("TAGS"))
        assert len(tags_edges) == 1
        assert tags_edges[0].src == "v1.0.0" and tags_edges[0].dst == commit_hash

    def test_no_tags_yields_empty_graph(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        ctx = _make_ctx(tmp_path)
        g = releases.extract(ctx)
        assert list(g.nodes("Release")) == []


class TestBuildSymbols:
    def test_functions_classes_and_calls_extracted(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text(
            "class Greeter:\n"
            "    def greet(self, name):\n"
            "        return _format(name)\n"
            "\n"
            "\n"
            "def _format(name):\n"
            "    return f'hi {name}'\n"
        )
        _git(tmp_path, "add", "app.py")
        _git(tmp_path, "commit", "-q", "-m", "add greeter")

        g = build_symbols.extract(tmp_path)

        symbol_keys = {s.natural_key for s in g.nodes("Symbol")}
        assert "app.py::Greeter" in symbol_keys
        assert "app.py::Greeter.greet" in symbol_keys
        assert "app.py::_format" in symbol_keys

        greet = next(s for s in g.nodes("Symbol") if s.natural_key == "app.py::Greeter.greet")
        assert greet.props["kind"] == "method"
        fmt = next(s for s in g.nodes("Symbol") if s.natural_key == "app.py::_format")
        assert fmt.props["kind"] == "function"
        assert fmt.props["is_public"] is False

        calls = list(g.edges("CALLS"))
        assert any(
            e.src == "app.py::Greeter.greet" and e.dst == "app.py::_format" for e in calls
        )

    def test_defined_in_target_file_node_exists_in_same_graph(self, tmp_path: Path) -> None:
        """Regression guard: DEFINED_IN's own File target must be a real
        node build_symbols.py itself adds -- confirmed live this was
        missing, which made devkb/build.py's load_cache() silently drop
        every DEFINED_IN edge on merge (no uid->natural_key entry to
        resolve the File side against)."""
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text("def f():\n    pass\n")
        _git(tmp_path, "add", "app.py")
        _git(tmp_path, "commit", "-q", "-m", "x")

        g = build_symbols.extract(tmp_path)

        file_keys = {f.natural_key for f in g.nodes("File")}
        assert "app.py" in file_keys
        defined_in = list(g.edges("DEFINED_IN"))
        assert len(defined_in) == 1
        assert defined_in[0].dst == "app.py"

    def test_unparseable_file_yields_no_symbols_not_a_crash(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "broken.py").write_text("def f(:\n")  # invalid syntax
        _git(tmp_path, "add", "broken.py")
        _git(tmp_path, "commit", "-q", "-m", "x")
        g = build_symbols.extract(tmp_path)
        assert list(g.nodes("Symbol")) == []

    def test_load_cache_round_trips_nodes_and_edges(self, tmp_path: Path) -> None:
        """build() itself goes through project_context.resolve(), which
        needs a real projects.json registration -- exercised live instead
        (devkb build_symbols.py --project PATH). Here: write the
        cache files the same way build() would, using a ctx built directly
        via _make_ctx, and confirm load_cache() reconstructs the same
        nodes/edges -- the round-trip logic under test, independent of
        project registration."""
        _init_repo(tmp_path)
        (tmp_path / "app.py").write_text("def a():\n    return b()\n\n\ndef b():\n    return 1\n")
        _git(tmp_path, "add", "app.py")
        _git(tmp_path, "commit", "-q", "-m", "x")

        ctx = _make_ctx(tmp_path)
        graph = build_symbols.extract(tmp_path)
        ctx.devkb_dir.mkdir(parents=True, exist_ok=True)
        data = graph.to_dict()
        (ctx.devkb_dir / "symbols-nodes.jsonl").write_text(
            "\n".join(json.dumps(n) for n in data["nodes"]) + "\n"
        )
        (ctx.devkb_dir / "symbols-edges.jsonl").write_text(
            "\n".join(json.dumps(e) for e in data["edges"]) + "\n"
        )

        loaded = build_symbols.load_cache(ctx)

        assert {n.natural_key for n in loaded.nodes("Symbol")} == {n.natural_key for n in graph.nodes("Symbol")}
        assert {n.natural_key for n in loaded.nodes("File")} == {n.natural_key for n in graph.nodes("File")}
        assert loaded.edge_count() == graph.edge_count()
        defined_in = list(loaded.edges("DEFINED_IN"))
        assert len(defined_in) == 2  # a() and b() each defined in app.py
        assert all(e.dst == "app.py" for e in defined_in)
        calls = list(loaded.edges("CALLS"))
        assert any(e.src == "app.py::a" and e.dst == "app.py::b" for e in calls)

    def test_load_cache_empty_when_no_refresh_has_run(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        g = build_symbols.load_cache(ctx)
        assert list(g.nodes()) == []
