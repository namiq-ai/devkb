"""Where a project's tests are, and which test functions they hold (ODSF-304).

devkb used to look for tests under `<repo>/tests` only. ODSF keeps its tests in
`pms-backend/tests/` and `sdp/devsecops/automation/`, and another keeps them in
`tests/`, `ai-gateway/tests/` and `kb-service/tests/`, so the graph reported
0 of about 2,070 test functions for ODSF and 157 of about 2,777 for another. A
graph that answers "what tests this?" from a fraction of the tests is worse
than no graph, because it answers confidently.

Discovery is by file name over `git ls-files` (so `.gitignore` is honoured and
there is no exclusion list to keep in sync), not by directory, so a project
cannot hide tests by putting them somewhere new.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

_PY_TEST = re.compile(r"(^|/)(test_[^/]+|[^/]+_test)\.py$")
_JS_TEST = re.compile(r"(^|/)[^/]+\.(test|spec)\.[cm]?[jt]sx?$")
# C#: a file in a test project (`Foo.Tests/`, `FooTests/`, `tests/`, `test/`) or named `*Test.cs` / `*Tests.cs`.
_CS_TEST = re.compile(r"(^|/)([^/]*\.Tests?|[^/]*Tests|[Tt]ests?|[^/]*\.(Unit|Integration)Tests?)/(?:[^/]+/)*[^/]+\.cs$"
                      r"|(^|/)[^/]+Tests?\.cs$")
# A path segment that means "not this project's own tests".
_SKIP = re.compile(r"(^|/)(node_modules|\.impl-worktrees|\.claude|vendor|output)/")
_JS_CASE = re.compile(
    r"^\s*(?:it|test)(?:\.(?:only|skip|todo))?\s*\(\s*(['\"`])(.+?)\1", re.MULTILINE,
)


def list_test_files(repo_root: Path, tests_dir: Path | None = None) -> list[str]:
    """Repo-relative paths of every tracked test file, sorted.

    `tests_dir`, when given and present, is walked too (every `.py` under it),
    which keeps the pre-ODSF-304 behaviour for a test file that exists on disk
    but is not yet committed: a developer's new test is still seen."""
    proc = subprocess.run(
        ["git", "ls-files", "--recurse-submodules"], cwd=repo_root, capture_output=True, text=True, check=False,
    )
    found = []
    for rel in proc.stdout.splitlines():
        if not rel or _SKIP.search(rel):
            continue
        if _PY_TEST.search(rel) or _JS_TEST.search(rel) or _CS_TEST.search(rel):
            found.append(rel)
    if tests_dir is not None and tests_dir.is_dir():
        for path in tests_dir.rglob("*.py"):
            rel = path.relative_to(repo_root).as_posix()
            if not _SKIP.search(rel):
                found.append(rel)
    return sorted(set(found))


def tests_in_file(repo_root: Path, rel: str) -> list[tuple[str, int]]:
    """[(test name, 1-based line), ...] for one test file. Unreadable or
    unparseable files yield nothing rather than raising: one broken file must
    not hide the rest of a project's tests."""
    path = repo_root / rel
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    if rel.endswith(".py"):
        try:
            tree = ast.parse(text, filename=rel)
        except (SyntaxError, ValueError):
            return []
        return sorted(
            (node.name, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    if rel.endswith(".cs"):
        from devkb.csharp_symbols import tests_in_text  # noqa: PLC0415
        return tests_in_text(text)
    out = []
    for match in _JS_CASE.finditer(text):
        out.append((match.group(2), text.count("\n", 0, match.start()) + 1))
    return out
