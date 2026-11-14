"""File cross-reference + test-marker extractor (devkb Phase 2, ODSF-032).

Ports the two remaining halves of an earlier traceability script's
logic that Phase 1 (tickets_git.py) didn't already cover: `_git_files_changed`
(commit -> files touched) and `_find_test_markers` (which test files/functions
mention a ticket), generalized off OCO's hardcoded `OCO-` prefix strip to this
project's own ctx.ticket_prefix.

Takes the already-built tickets_git graph as an argument instead of round-
tripping through a previous .devkb/edges.jsonl build on disk (the roadmap's
literal "input: .devkb/edges.jsonl's REFERENCES" wording) -- same information
(which commits reference which ticket), but no ordering/staleness risk on a
project's very first build, when no prior .devkb/ store exists yet.
"""
from __future__ import annotations

import re
from pathlib import Path

from devkb.extractors.tickets_git import _run
from devkb.test_discovery import list_test_files
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext

_TEST_FUNC_RE = re.compile(r"^\s*def (test_\w+)\s*\(")

# Ticket-mediated File->TestCase fan-out is inherently coarse (every file a
# ticket's commits touched gets linked to every test marker that ticket has),
# so a ticket with an unusually large touched-file set produces a
# disproportionate number of low-signal edges. Confirmed live against OCO:
# one ticket's commit list included a mass file-move (~650 files after fixing
# the git --grep anchoring bug below, ~20k before) -- past a certain size the
# "touched by this ticket" relationship stops being a meaningful coverage
# signal regardless of anchoring. p90 of OCO's own real per-ticket
# touched-file counts is 28; 50 keeps the vast majority of normal tickets
# while excluding the long tail.
_MAX_TOUCHED_FILES_FOR_TESTED_BY = 50

# ODSF-314. A commit touching more files than this is a bulk change (an archive rename, a mass reformat): in OCO 38 of
# 5,132 commits produced 40% of every TOUCHES edge, and "commit X touched file F" says nothing about F. Such a commit
# keeps its node, with `files_changed` and `bulk`, but emits no TOUCHES.
BULK_COMMIT_FILES = 200

# ODSF-314. Ticket-marker TESTED_BY ("a test names ticket T, so it covers every file T's commits touched") measured
# 0.7% precision on OCO (600 sampled edges; the test body called something in the file in 4). It is kept, as the
# owner chose, but only from files that hold code, under a lower cap, with a confidence that says what it is.
_MARKER_CAP = 20
_MARKER_CONFIDENCE = 0.2
_CODE_FILE = re.compile(r"\.(py|ts|tsx|js|jsx|mjs)$")
_TEST_PATH = re.compile(r"(^|/)(tests?/|test_[^/]*$|[^/]*_test\.py$|[^/]*\.(test|spec)\.[jt]sx?$|conftest\.py$)")


def is_bulk(files: list[str] | set[str]) -> bool:
    return len(files) > BULK_COMMIT_FILES


def _files_touched(commit_hash: str, repo_root: Path) -> list[str]:
    # --root: without it, diff-tree on a commit with no parent (the repo's
    # very first commit) has nothing to diff against and silently returns no
    # files -- a real gap in the traceability.py logic this ports (same
    # command, minus --root), just never exercised there against a root
    # commit. Safe to always pass: it only changes root-commit behavior,
    # normal commits with a parent are unaffected.
    out = _run(["git", "diff-tree", "--no-commit-id", "-r", "--root", "--name-only", commit_hash], repo_root)
    return [f for f in out.splitlines() if f]


def _load_test_files(
    tests_dir: Path, repo_root: Path, files: list[Path] | None = None,
) -> list[tuple[str, str, list[str]]]:
    """Reads every test file from disk exactly once -- (rel_path, full_text,
    lines) per file. Callers scan this in-memory list per ticket instead of
    re-reading disk per ticket (see _scan_test_files' own docstring for why
    that distinction matters).

    `files` (ODSF-304), when given, replaces the `tests_dir` walk: the caller
    has already found every test file in the repo, wherever it lives."""
    if files is None:
        if not tests_dir.exists():
            return []
        files = sorted(tests_dir.rglob("*.py"))
    out: list[tuple[str, str, list[str]]] = []
    for py in files:
        try:
            content = py.read_text(errors="replace")
        except OSError:
            continue
        out.append((str(py.relative_to(repo_root)), content, content.splitlines()))
    return out


def _scan_test_files(
    ticket: str, test_files: list[tuple[str, str, list[str]]],
) -> list[tuple[str, int, str | None, str]]:
    """Deliberately narrower than traceability.py::_find_test_markers, which
    also matched `ticket.*<short-id>` and `mark.*<ticket>` (e.g. bare `100`
    near the word "ticket"). That's fine for a human-read CLI report — a
    reader visually discounts an obvious false positive — but wrong for a
    persisted graph edge with no human filter: confirmed live against OCO,
    those two loose patterns alone pushed "tickets with a test marker" past
    1,100 of ~1,265, most of it short-numeric-id noise (a 2-3 digit ticket
    number is a common substring in test code for unrelated reasons — ports,
    counts, HTTP statuses). The full anchored ticket id alone is still real,
    substantial signal (OCO's own tests/ conventions actively encourage
    `@pytest.mark.ticket("OCO-NNN")`/`test_OCO_NNN_*`), just without the
    noise floor. \\b-anchored for the same reason as tickets_git.py's own
    _git_commits fix: "OCO-100" must not match inside "OCO-1000".
    Returns (path, line 1-indexed, enclosing test function name if found,
    matched line text) per hit -- the enclosing-function walk is new here
    (traceability.py's own CLI report didn't need a stable per-hit key;
    devkb's TestCase natural_key does)."""
    pattern = re.compile(rf"\b{re.escape(ticket)}\b")
    hits: list[tuple[str, int, str | None, str]] = []
    for path, content, lines in test_files:
        if not pattern.search(content):
            continue
        for i, line in enumerate(lines):
            if not pattern.search(line):
                continue
            func = None
            for j in range(i, -1, -1):
                m = _TEST_FUNC_RE.match(lines[j])
                if m:
                    func = m.group(1)
                    break
            hits.append((path, i + 1, func, line.strip()))
    return hits


def _find_test_markers(
    ticket: str, tests_dir: Path, repo_root: Path,
) -> list[tuple[str, int, str | None, str]]:
    """Single-ticket convenience wrapper over _load_test_files/_scan_test_files.
    extract() itself below calls _load_test_files once and _scan_test_files
    per ticket instead of this -- confirmed live that this straight port's
    original per-ticket-rglob-and-read version never finished a build against
    OCO (~1,300+ archived tickets x 184 test files = hundreds of thousands of
    file reads) inside a 2-minute window."""
    return _scan_test_files(ticket, _load_test_files(tests_dir, repo_root))


def extract(
    ctx: ProjectContext, tickets_graph: DevKBGraph,
    precomputed_touches: dict[str, list[str]] | None = None,
) -> DevKBGraph:
    """precomputed_touches (commit hash -> touched file paths), when given,
    lets a caller that already ran `git diff-tree` for a commit (BL-1's
    source_baseline.py, which walks ALL commits, not just ticket-referenced
    ones -- its own commit set is normally a superset of this function's)
    skip paying that subprocess cost twice for the same commit. Correctness
    is unaffected either way -- DevKBGraph dedupes -- this is purely a
    performance path."""
    g = DevKBGraph()
    precomputed_touches = precomputed_touches or {}

    seen_commits: set[str] = set()
    for commit in tickets_graph.nodes("Commit"):
        h = commit.natural_key
        if h in seen_commits:
            continue
        seen_commits.add(h)
        touched = precomputed_touches.get(h)
        if touched is None:
            touched = _files_touched(h, ctx.repo_root)
        if is_bulk(touched):
            g.add_node("Commit", h, source="git-diff-tree", files_changed=len(touched), bulk=True)
            continue
        for path in touched:
            g.add_node("File", path, source="git-diff-tree")
            g.add_edge(
                "TOUCHES", "Commit", h, "File", path,
                source="git-diff-tree", confidence=1.0,
                evidence_ref=f"git diff-tree --name-only {h[:10]}",
            )

    # Ticket -> its touched files, precomputed once so the per-marker loop
    # below doesn't re-walk REFERENCES/TOUCHES edges per hit.
    files_by_ticket: dict[str, set[str]] = {}
    commit_to_ticket = {e.src: e.dst for e in tickets_graph.edges("REFERENCES")}
    for edge in g.edges("TOUCHES"):
        ticket = commit_to_ticket.get(edge.src)
        if ticket:
            files_by_ticket.setdefault(ticket, set()).add(edge.dst)

    # ODSF-304: every tracked python test file, not only those under tests/.
    test_files = _load_test_files(
        ctx.tests_dir, ctx.repo_root,
        files=[ctx.repo_root / rel for rel in list_test_files(ctx.repo_root, ctx.tests_dir) if rel.endswith(".py")],
    )
    for ticket_node in tickets_graph.nodes("Ticket"):
        ticket = ticket_node.natural_key
        touched_files = files_by_ticket.get(ticket, set())
        # Past _MAX_TOUCHED_FILES_FOR_TESTED_BY, "this ticket's commits
        # touched file X" stops being a meaningful per-file signal (a
        # mass-rename/move ticket touches everything, not "everything this
        # ticket is about") -- the TestCase node below still gets created
        # either way, only the fan-out edges are skipped for an oversized
        # ticket, so the marker itself is never silently dropped.
        code_files = {f for f in touched_files if _CODE_FILE.search(f) and not _TEST_PATH.search(f)}
        link_files = code_files if len(code_files) <= _MARKER_CAP else set()
        for path, line, func, snippet in _scan_test_files(ticket, test_files):
            test_key = f"{path}:{line}"
            g.add_node(
                "TestCase", test_key, source="tests",
                file=path, line=line, function=func, ticket=ticket, snippet=snippet,
            )
            # File -> TestCase is ticket-mediated (same coarse grain
            # traceability.py's own report used: a test that mentions the
            # ticket "covers" every file that ticket's commits touched, not
            # a content-level coverage analysis) -- includes the test file
            # itself if a commit also touched it, which is correct, not
            # redundant: that commit really did change the test.
            for file_path in link_files:
                g.add_edge(
                    "TESTED_BY", "File", file_path, "TestCase", test_key,
                    source="test-marker-grep", confidence=_MARKER_CONFIDENCE,
                    evidence_ref=f"{path}:{line} references {ticket}", extra={"kind": "ticket-marker"},
                )

    return g
