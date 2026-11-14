"""Tests for ODSF-032: devkb Phase 2 -- File/TestCase extraction and the
Module<->File translation bridge.

Covers:
  1. devkb.model -- File/TestCase/TOUCHES/TESTED_BY are governed (ADR-SDP-
     DEVKB-001 Phase 2 amendment), not silently addable elsewhere.
  2. devkb.extractors.files_tests -- _find_test_markers' enclosing-function
     walk, and extract()'s end-to-end File/TOUCHES/TestCase/TESTED_BY output
     against a real (tiny, throwaway) git repo -- _files_touched shells out
     to `git diff-tree`, so a fake commit hash can't stand in for this.
  3. devkb.module_file_bridge -- exact Module->File path arithmetic (service
     root + module's own recorded file property, not a dotted-name guess),
     both directions, and the "no discovery graph yet" empty-dict case.
  4. devkb.query.context_bundle -- a File node's bundle gets discovery_module
     enrichment when a matching discovery/graph.json exists.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import model, module_file_bridge, query  # noqa: E402
from devkb.extractors import files_tests  # noqa: E402
from devkb.index import DevKBIndex  # noqa: E402
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


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _init_repo_with_one_commit(root: Path) -> str:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "app.py").write_text("print('hi')\n")
    _git(root, "add", "app.py")
    _git(root, "commit", "-q", "-m", "TST-1: initial commit")
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
    return out.stdout.strip()


# ══════════════════════════════════════════════════════════════════════════════
# devkb.model -- Phase 2 governance
# ══════════════════════════════════════════════════════════════════════════════

def test_phase2_node_types_and_verbs_are_governed() -> None:
    assert "File" in model.NODE_TYPES
    assert "TestCase" in model.NODE_TYPES
    assert "TOUCHES" in model.VERBS
    assert "TESTED_BY" in model.VERBS


# ══════════════════════════════════════════════════════════════════════════════
# devkb.extractors.files_tests
# ══════════════════════════════════════════════════════════════════════════════

class TestFindTestMarkers:
    def test_finds_ticket_mention_and_enclosing_function(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text(
            "def test_something():\n"
            "    # covers TST-1\n"
            "    assert True\n"
        )
        hits = files_tests._find_test_markers("TST-1", tests_dir, tmp_path)
        assert len(hits) == 1
        path, line, func, snippet = hits[0]
        assert path == "tests/test_foo.py"
        assert line == 2
        assert func == "test_something"
        assert "TST-1" in snippet

    def test_no_tests_dir_returns_empty(self, tmp_path: Path) -> None:
        assert files_tests._find_test_markers("TST-1", tmp_path / "nope", tmp_path) == []

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text("def test_unrelated():\n    assert True\n")
        assert files_tests._find_test_markers("TST-1", tests_dir, tmp_path) == []

    def test_short_id_near_ticket_word_is_not_matched(self, tmp_path: Path) -> None:
        """Regression guard for the noise this deliberately dropped: a bare
        short numeric id near the word "ticket"/"mark" must NOT register as a
        hit for TST-1 just because both words appear somewhere in the line."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text(
            "def test_unrelated():\n"
            "    # ticket queue holds up to 1 item per mark cycle\n"
            "    assert True\n"
        )
        assert files_tests._find_test_markers("TST-1", tests_dir, tmp_path) == []

    def test_full_id_is_boundary_anchored(self, tmp_path: Path) -> None:
        """TST-1 must not match inside TST-10 -- same class of bug as
        tickets_git.py's own _git_commits anchoring fix."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text("def test_other():\n    # covers TST-10\n    assert True\n")
        assert files_tests._find_test_markers("TST-1", tests_dir, tmp_path) == []


class TestExtract:
    def test_end_to_end_file_touches_and_tested_by(self, tmp_path: Path) -> None:
        commit_hash = _init_repo_with_one_commit(tmp_path)
        ctx = _make_ctx(tmp_path)

        tickets_graph = DevKBGraph()
        tickets_graph.add_node("Ticket", "TST-1", source="tickets", title="x")
        tickets_graph.add_node("Commit", commit_hash, source="git")
        tickets_graph.add_edge(
            "REFERENCES", "Commit", commit_hash, "Ticket", "TST-1", source="git-log-grep",
        )

        (ctx.tests_dir).mkdir()
        (ctx.tests_dir / "test_app.py").write_text(
            "def test_app_behaviour():\n"
            "    # ticket TST-1\n"
            "    assert True\n"
        )

        g = files_tests.extract(ctx, tickets_graph)

        files = list(g.nodes("File"))
        assert [f.natural_key for f in files] == ["app.py"]

        touches = list(g.edges("TOUCHES"))
        assert len(touches) == 1
        assert touches[0].src == commit_hash and touches[0].dst == "app.py"

        test_cases = list(g.nodes("TestCase"))
        assert len(test_cases) == 1
        assert test_cases[0].natural_key == "tests/test_app.py:2"
        assert test_cases[0].props["function"] == "test_app_behaviour"

        tested_by = list(g.edges("TESTED_BY"))
        assert len(tested_by) == 1
        assert tested_by[0].src == "app.py"
        assert tested_by[0].dst == "tests/test_app.py:2"
        assert tested_by[0].confidence == 0.2  # ODSF-314: measured 0.7% precision on OCO; was 0.7

    def test_no_matching_tests_yields_no_testcase_nodes(self, tmp_path: Path) -> None:
        commit_hash = _init_repo_with_one_commit(tmp_path)
        ctx = _make_ctx(tmp_path)
        tickets_graph = DevKBGraph()
        tickets_graph.add_node("Ticket", "TST-1", source="tickets", title="x")
        tickets_graph.add_node("Commit", commit_hash, source="git")
        tickets_graph.add_edge("REFERENCES", "Commit", commit_hash, "Ticket", "TST-1", source="git-log-grep")

        g = files_tests.extract(ctx, tickets_graph)

        assert [f.natural_key for f in g.nodes("File")] == ["app.py"]
        assert list(g.nodes("TestCase")) == []
        assert list(g.edges("TESTED_BY")) == []

    def test_oversized_touched_file_set_skips_tested_by_but_keeps_testcase(self, tmp_path: Path) -> None:
        """A ticket whose commit touched more than
        _MAX_TOUCHED_FILES_FOR_TESTED_BY files (a mass-rename/move, not a
        real "this ticket is about these files" relationship) must not fan
        out into that many low-signal TESTED_BY edges -- but the TestCase
        marker itself is still real and must not be silently dropped."""
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "config", "user.email", "test@example.com")
        _git(tmp_path, "config", "user.name", "Test")
        n = files_tests._MAX_TOUCHED_FILES_FOR_TESTED_BY + 1
        for i in range(n):
            (tmp_path / f"file{i}.py").write_text("x = 1\n")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "TST-1: mass add")
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True,
        ).stdout.strip()

        ctx = _make_ctx(tmp_path)
        tickets_graph = DevKBGraph()
        tickets_graph.add_node("Ticket", "TST-1", source="tickets", title="x")
        tickets_graph.add_node("Commit", commit_hash, source="git")
        tickets_graph.add_edge("REFERENCES", "Commit", commit_hash, "Ticket", "TST-1", source="git-log-grep")

        ctx.tests_dir.mkdir()
        (ctx.tests_dir / "test_app.py").write_text("def test_x():\n    # covers TST-1\n    assert True\n")

        g = files_tests.extract(ctx, tickets_graph)

        assert len(list(g.nodes("File"))) == n
        assert len(list(g.nodes("TestCase"))) == 1
        assert list(g.edges("TESTED_BY")) == []


# ══════════════════════════════════════════════════════════════════════════════
# devkb.module_file_bridge
# ══════════════════════════════════════════════════════════════════════════════

class TestModuleFileBridge:
    def _write_discovery_graph(self, tmp_path: Path, service_root: Path) -> Path:
        graph_path = tmp_path / "graph.json"
        graph_path.write_text(json.dumps({
            "nodes": [
                {"type": "Service", "natural_key": "svc", "root": str(service_root)},
                {"type": "Module", "natural_key": "svc.pkg.mod", "service": "svc", "file": "pkg/mod.py"},
            ],
        }))
        return graph_path

    def test_build_module_to_file(self, tmp_path: Path) -> None:
        service_root = tmp_path / "svc"
        service_root.mkdir()
        graph_path = self._write_discovery_graph(tmp_path, service_root)

        mapping = module_file_bridge.build_module_to_file(graph_path, tmp_path)
        assert mapping == {"svc.pkg.mod": "svc/pkg/mod.py"}

    def test_file_to_module_is_the_inverse(self, tmp_path: Path) -> None:
        service_root = tmp_path / "svc"
        service_root.mkdir()
        graph_path = self._write_discovery_graph(tmp_path, service_root)

        assert module_file_bridge.file_to_module(graph_path, tmp_path) == {"svc/pkg/mod.py": "svc.pkg.mod"}

    def test_missing_graph_returns_empty_dict(self, tmp_path: Path) -> None:
        assert module_file_bridge.build_module_to_file(tmp_path / "nope.json", tmp_path) == {}

    def test_service_root_outside_repo_is_skipped(self, tmp_path: Path) -> None:
        outside_root = tmp_path.parent / f"outside-{tmp_path.name}"
        graph_path = self._write_discovery_graph(tmp_path, outside_root)
        assert module_file_bridge.build_module_to_file(graph_path, tmp_path) == {}


# ══════════════════════════════════════════════════════════════════════════════
# devkb.query.context_bundle -- File enrichment
# ══════════════════════════════════════════════════════════════════════════════

def test_context_bundle_enriches_file_with_discovery_module(tmp_path: Path) -> None:
    onboarding = tmp_path / ".onboarding"
    onboarding.mkdir()
    service_root = tmp_path / "svc"
    service_root.mkdir()
    (onboarding / "graph.json").write_text(json.dumps({
        "nodes": [
            {"type": "Service", "natural_key": "svc", "root": str(service_root)},
            {"type": "Module", "natural_key": "svc.pkg.mod", "service": "svc", "file": "pkg/mod.py"},
        ],
    }))

    file_node = {
        "uid": model.uid_for("File", "svc/pkg/mod.py"),
        "type": "File", "natural_key": "svc/pkg/mod.py", "source": "git-diff-tree",
        "properties": {},
    }
    idx = DevKBIndex()
    idx.by_uid[file_node["uid"]] = file_node
    idx.by_type["File"].append(file_node)
    idx.by_natural_key[("File", "svc/pkg/mod.py")] = file_node

    ctx = _make_ctx(tmp_path)
    bundle = query.context_bundle(idx, "svc/pkg/mod.py", ctx)

    assert bundle["found"] is True
    assert bundle["node"]["properties"]["discovery_module"] == "svc.pkg.mod"


def test_context_bundle_file_without_discovery_graph_is_unenriched(tmp_path: Path) -> None:
    file_node = {
        "uid": model.uid_for("File", "app.py"),
        "type": "File", "natural_key": "app.py", "source": "git-diff-tree",
        "properties": {},
    }
    idx = DevKBIndex()
    idx.by_uid[file_node["uid"]] = file_node
    idx.by_type["File"].append(file_node)
    idx.by_natural_key[("File", "app.py")] = file_node

    ctx = _make_ctx(tmp_path)
    bundle = query.context_bundle(idx, "app.py", ctx)

    assert bundle["found"] is True
    assert "discovery_module" not in bundle["node"]["properties"]
