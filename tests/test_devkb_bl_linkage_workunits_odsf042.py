"""Tests for ODSF-042: devkb BL-4/BL-6 -- content-based test linkage and
commit-cluster inference (body/legs model, devkb/ROADMAP.md).

Covers:
  1. devkb.extractors.symbol_tests (BL-4) -- a test function's own imports
     + calls (not "the file mentions it somewhere") resolve to a real
     TESTED_BY edge against a Symbol, no ticket involved.
  2. devkb.extractors.work_units (BL-6, deterministic half) -- same-day +
     same-author + touched-file-overlap clustering of ticket-unreferenced
     commits into WorkUnit nodes, confidence 0.5 throughout, and that a
     real ticket-referenced commit is correctly excluded from clustering.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb.extractors import symbol_tests, work_units  # noqa: E402
from devkb.model import DevKBGraph  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _make_ctx(repo_root: Path, code: str = "TST") -> ProjectContext:
    return ProjectContext(
        code=code, repo_root=repo_root, ticket_prefix=code,
        issues_dir=repo_root / "issues", tests_dir=repo_root / "tests",
        sprint_dir=repo_root / "historical" / "sprints", devkb_dir=repo_root / ".devkb",
        board_file=repo_root / "sdp" / "data" / "PROJECT_BOARD.md",
        wp_map_file=repo_root / "sdp" / "data" / "orchestrator" / "wp-map.json",
    )


class TestSymbolTests:
    def test_imported_and_called_symbol_gets_tested_by(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text(
            "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        )

        graph = DevKBGraph()
        graph.add_node("Symbol", "app.py::add", source="ast", kind="function")
        graph.add_node("File", "app.py", source="ast")
        graph.add_edge("DEFINED_IN", "Symbol", "app.py::add", "File", "app.py", source="ast")

        ctx = _make_ctx(tmp_path)
        g = symbol_tests.extract(ctx, graph)

        tested_by = list(g.edges("TESTED_BY"))
        assert len(tested_by) == 1
        assert tested_by[0].src == "app.py::add"
        assert tested_by[0].dst == "tests/test_app.py:4"
        assert tested_by[0].confidence == 0.95

    def test_import_not_called_in_this_test_function_is_not_linked(self, tmp_path: Path) -> None:
        """Precision guard: a name imported at file scope but only called
        by a DIFFERENT test function must not attribute to this one --
        the exact file-level coarseness this extractor exists to avoid."""
        (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\ndef sub(a, b):\n    return a - b\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text(
            "from app import add, sub\n\n\n"
            "def test_add():\n    assert add(1, 2) == 3\n\n\n"
            "def test_sub():\n    assert sub(2, 1) == 1\n"
        )

        graph = DevKBGraph()
        graph.add_node("Symbol", "app.py::add", source="ast", kind="function")
        graph.add_node("Symbol", "app.py::sub", source="ast", kind="function")
        graph.add_node("File", "app.py", source="ast")

        ctx = _make_ctx(tmp_path)
        g = symbol_tests.extract(ctx, graph)

        by_test = {}
        for e in g.edges("TESTED_BY"):
            by_test.setdefault(e.dst, set()).add(e.src)
        test_add_key = "tests/test_app.py:4"
        test_sub_key = "tests/test_app.py:8"
        assert by_test[test_add_key] == {"app.py::add"}
        assert by_test[test_sub_key] == {"app.py::sub"}

    def test_no_symbols_yields_empty_graph(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("def test_x():\n    assert True\n")
        ctx = _make_ctx(tmp_path)
        g = symbol_tests.extract(ctx, DevKBGraph())
        assert list(g.edges("TESTED_BY")) == []

    def test_no_tests_dir_yields_empty_graph(self, tmp_path: Path) -> None:
        graph = DevKBGraph()
        graph.add_node("Symbol", "app.py::add", source="ast", kind="function")
        ctx = _make_ctx(tmp_path)
        g = symbol_tests.extract(ctx, graph)
        assert list(g.edges("TESTED_BY")) == []


class TestWorkUnits:
    def _commit(self, graph: DevKBGraph, sha: str, date: str, author: str) -> None:
        graph.add_node("Commit", sha, source="git-log-baseline", date=date, author=author, subject=sha)

    def _touch(self, graph: DevKBGraph, sha: str, path: str) -> None:
        graph.add_node("File", path, source="git-log-baseline")
        graph.add_edge("TOUCHES", "Commit", sha, "File", path, source="git-log-baseline")

    def test_same_day_same_author_overlapping_files_cluster_together(self, tmp_path: Path) -> None:
        graph = DevKBGraph()
        self._commit(graph, "a" * 40, "2026-08-01", "alice")
        self._commit(graph, "b" * 40, "2026-08-01", "alice")
        self._touch(graph, "a" * 40, "app.py")
        self._touch(graph, "b" * 40, "app.py")

        ctx = _make_ctx(tmp_path)
        g = work_units.extract(ctx, graph)

        units = list(g.nodes("WorkUnit"))
        assert len(units) == 1
        assert units[0].props["commit_count"] == 2
        groups = list(g.edges("GROUPS"))
        assert {e.dst for e in groups} == {"a" * 40, "b" * 40}
        assert all(e.confidence == 0.5 for e in groups)

    def test_different_author_splits_into_separate_units(self, tmp_path: Path) -> None:
        graph = DevKBGraph()
        self._commit(graph, "a" * 40, "2026-08-01", "alice")
        self._commit(graph, "b" * 40, "2026-08-01", "bob")
        self._touch(graph, "a" * 40, "app.py")
        self._touch(graph, "b" * 40, "app.py")

        ctx = _make_ctx(tmp_path)
        g = work_units.extract(ctx, graph)

        assert len(list(g.nodes("WorkUnit"))) == 2

    def test_different_day_splits_into_separate_units(self, tmp_path: Path) -> None:
        graph = DevKBGraph()
        self._commit(graph, "a" * 40, "2026-08-01", "alice")
        self._commit(graph, "b" * 40, "2026-08-05", "alice")
        self._touch(graph, "a" * 40, "app.py")
        self._touch(graph, "b" * 40, "app.py")

        ctx = _make_ctx(tmp_path)
        g = work_units.extract(ctx, graph)

        assert len(list(g.nodes("WorkUnit"))) == 2

    def test_ticket_referenced_commit_is_excluded_from_clustering(self, tmp_path: Path) -> None:
        graph = DevKBGraph()
        self._commit(graph, "a" * 40, "2026-08-01", "alice")
        graph.add_node("Ticket", "TST-1", source="tickets")
        graph.add_edge("REFERENCES", "Commit", "a" * 40, "Ticket", "TST-1", source="git-log-grep")

        ctx = _make_ctx(tmp_path)
        g = work_units.extract(ctx, graph)

        assert list(g.nodes("WorkUnit")) == []

    def test_work_unit_is_never_typed_ticket(self, tmp_path: Path) -> None:
        graph = DevKBGraph()
        self._commit(graph, "a" * 40, "2026-08-01", "alice")
        ctx = _make_ctx(tmp_path)
        g = work_units.extract(ctx, graph)
        assert list(g.nodes("Ticket")) == []
        assert len(list(g.nodes("WorkUnit"))) == 1
