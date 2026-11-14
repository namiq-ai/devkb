"""Tests for ODSF-033: devkb Phase 3 -- Warning nodes, FLAGGED_BY edges, and
open/resolved lifecycle tracking across builds.

Uses a small fake dev_compliance_monitor.py (same CLI contract: --check-all,
--since, --dry-run, --json-report PATH) written into tmp_path rather than
invoking ODSF's own real compliance rules -- keeps these tests fast,
deterministic, and independent of this repo's own live compliance state.
"""
from __future__ import annotations

import pytest

import hashlib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import model  # noqa: E402
from devkb.extractors import warnings  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402


def _make_ctx(repo_root: Path, code: str = "TST") -> ProjectContext:
    return ProjectContext(
        code=code, repo_root=repo_root, ticket_prefix=code,
        issues_dir=repo_root / "issues", tests_dir=repo_root / "tests",
        sprint_dir=repo_root / "historical" / "sprints", devkb_dir=repo_root / ".devkb",
        board_file=repo_root / "sdp" / "data" / "PROJECT_BOARD.md",
        wp_map_file=repo_root / "sdp" / "data" / "orchestrator" / "wp-map.json",
    )


def _write_fake_compliance_script(repo_root: Path, violations: list[dict]) -> None:
    script_path = repo_root / "sdp" / "devsecops" / "compliance" / "dev_compliance_monitor.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "import argparse, json, sys\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--check-all', action='store_true')\n"
        "ap.add_argument('--since', default='')\n"
        "ap.add_argument('--dry-run', action='store_true')\n"
        "ap.add_argument('--json-report', default='')\n"
        "args = ap.parse_args()\n"
        f"violations = {violations!r}\n"
        "if args.json_report:\n"
        "    with open(args.json_report, 'w') as f:\n"
        "        json.dump({'violations': violations}, f)\n"
        "sys.exit(0)\n"
    )


def test_phase3_node_type_and_verb_are_governed() -> None:
    assert "Warning" in model.NODE_TYPES
    assert "FLAGGED_BY" in model.VERBS


@pytest.fixture(autouse=True)
def _allow_repo_scripts(request, monkeypatch):
    if "default_off" not in request.node.name:
        monkeypatch.setenv("DEVKB_RUN_REPO_SCRIPTS", "1")


def test_default_off_the_repository_script_is_never_run(tmp_path: Path) -> None:
    """Analysing a repository must not execute its code unless the project opts in (run_repo_scripts)."""
    marker = tmp_path / "ran"
    script = tmp_path / "sdp/devsecops/compliance/dev_compliance_monitor.py"
    script.parent.mkdir(parents=True)
    script.write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    assert list(warnings.extract(_make_ctx(tmp_path)).nodes("Warning")) == []
    assert not marker.exists()


class TestExtractFiles:
    def test_path_line_pattern_matched_when_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("x = 1\n")
        found = warnings._extract_files("app.py:10: bad thing; other.py:2: also bad", tmp_path)
        assert found == ["app.py"]  # other.py doesn't exist on disk -- correctly excluded

    def test_file_prefix_pattern_matched_when_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / "issues").mkdir()
        (tmp_path / "issues" / "TST-1.md").write_text("# ticket\n")
        found = warnings._extract_files("File: issues/TST-1.md", tmp_path)
        assert found == ["issues/TST-1.md"]

    def test_no_match_when_nothing_exists_on_disk(self, tmp_path: Path) -> None:
        assert warnings._extract_files("Run: make wp-start WP=A-01", tmp_path) == []

    def test_process_level_evidence_yields_no_files(self, tmp_path: Path) -> None:
        assert warnings._extract_files("SHA: abc123def456", tmp_path) == []


class TestExtract:
    def test_no_compliance_script_yields_empty_graph(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        g = warnings.extract(ctx)
        assert list(g.nodes("Warning")) == []

    def test_end_to_end_warning_and_flagged_by(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("x = 1\n")
        _write_fake_compliance_script(tmp_path, [
            {"rule": "DEV-05", "severity": "HIGH", "detail": "OpenAI API URL found",
             "evidence": "app.py:3: some bad line"},
            {"rule": "DEV-08", "severity": "LOW", "detail": "no gate-release run",
             "evidence": "Run: make gate-release before merging"},
        ])
        ctx = _make_ctx(tmp_path)
        g = warnings.extract(ctx)

        warns = list(g.nodes("Warning"))
        assert len(warns) == 2
        by_rule = {w.props["rule"]: w for w in warns}
        assert by_rule["DEV-05"].props["severity"] == "HIGH"
        assert by_rule["DEV-08"].props["severity"] == "LOW"

        flagged = list(g.edges("FLAGGED_BY"))
        assert len(flagged) == 1
        assert flagged[0].src == "app.py"
        assert flagged[0].dst == by_rule["DEV-05"].natural_key

    def test_natural_key_is_sha256_of_rule_detail_and_evidence(self, tmp_path: Path) -> None:
        _write_fake_compliance_script(tmp_path, [
            {"rule": "DEV-08", "severity": "LOW", "detail": "x", "evidence": "Run: make gate-release"},
        ])
        ctx = _make_ctx(tmp_path)
        g = warnings.extract(ctx)
        w = next(g.nodes("Warning"))
        expected = hashlib.sha256("DEV-08:x:Run: make gate-release".encode()).hexdigest()
        assert w.natural_key == expected

    def test_distinct_violations_with_identical_boilerplate_evidence_dont_collide(self, tmp_path: Path) -> None:
        """Regression guard for the exact bug this was widened to fix: two
        real, distinct violations of the same rule sharing one fixed
        evidence string (DEV-07's own real shape) must not collapse into a
        single Warning node."""
        _write_fake_compliance_script(tmp_path, [
            {"rule": "DEV-07", "severity": "MEDIUM",
             "detail": "Schema change in 'a.md' without ADR: abc123 'subject one'",
             "evidence": "No ADR issue found in issues/ for recent schema change"},
            {"rule": "DEV-07", "severity": "MEDIUM",
             "detail": "Schema change in 'b.md' without ADR: def456 'subject two'",
             "evidence": "No ADR issue found in issues/ for recent schema change"},
        ])
        ctx = _make_ctx(tmp_path)
        g = warnings.extract(ctx)
        warns = list(g.nodes("Warning"))
        assert len(warns) == 2
        assert warns[0].natural_key != warns[1].natural_key


class TestApplyLifecycle:
    def test_first_seen_last_seen_on_first_build(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        g = model.DevKBGraph()
        g.add_node("Warning", "key1", source="dev-compliance-monitor",
                    rule="DEV-08", severity="LOW", detail="x", evidence="e")
        warnings.apply_lifecycle(ctx, g)
        w = next(g.nodes("Warning"))
        assert w.props["first_seen"] == w.props["last_seen"]
        assert w.props["resolved_at"] == ""
        assert w.props["status"] == "open"
        assert (ctx.devkb_dir / "warnings-history.jsonl").exists()

    def test_still_open_updates_last_seen_keeps_first_seen(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        g1 = model.DevKBGraph()
        g1.add_node("Warning", "key1", source="x", rule="DEV-08", severity="LOW", detail="x", evidence="e")
        warnings.apply_lifecycle(ctx, g1)
        first_seen_1 = next(g1.nodes("Warning")).props["first_seen"]

        g2 = model.DevKBGraph()
        g2.add_node("Warning", "key1", source="x", rule="DEV-08", severity="LOW", detail="x", evidence="e")
        warnings.apply_lifecycle(ctx, g2)
        w2 = next(g2.nodes("Warning"))
        assert w2.props["first_seen"] == first_seen_1
        assert w2.props["resolved_at"] == ""
        assert w2.props["status"] == "open"

    def test_resolved_warning_still_gets_a_node(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        g1 = model.DevKBGraph()
        g1.add_node("Warning", "key1", source="x", rule="DEV-08", severity="LOW", detail="x", evidence="e")
        warnings.apply_lifecycle(ctx, g1)

        g2 = model.DevKBGraph()  # empty -- warning no longer present in this scan
        warnings.apply_lifecycle(ctx, g2)

        w2 = next(g2.nodes("Warning"))
        assert w2.natural_key == "key1"
        assert w2.props["resolved_at"] is not None
        assert w2.props["status"] == "resolved"

    def test_reopened_warning_clears_resolved_at(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        g1 = model.DevKBGraph()
        g1.add_node("Warning", "key1", source="x", rule="DEV-08", severity="LOW", detail="x", evidence="e")
        warnings.apply_lifecycle(ctx, g1)

        g2 = model.DevKBGraph()
        warnings.apply_lifecycle(ctx, g2)  # resolved

        g3 = model.DevKBGraph()
        g3.add_node("Warning", "key1", source="x", rule="DEV-08", severity="LOW", detail="x", evidence="e")
        warnings.apply_lifecycle(ctx, g3)  # reopened

        w3 = next(g3.nodes("Warning"))
        assert w3.props["resolved_at"] == ""
        assert w3.props["status"] == "open"
