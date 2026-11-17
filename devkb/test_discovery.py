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
from dataclasses import dataclass
from pathlib import Path

from devkb import cpp_symbols

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


def pytest_testpaths(repo_root: Path) -> tuple[str, ...]:
    """The `testpaths` of the project's pytest configuration, () when it has none. The file pytest itself would use:
    pytest.ini, then pyproject.toml with [tool.pytest.ini_options], tox.ini with [pytest], setup.cfg with [tool:pytest].
    With testpaths set, a module named `test_*.py` outside them and outside any tests/ tree is source code, not a
    test (`devkb/test_discovery.py`, #71)."""
    import configparser  # noqa: PLC0415

    def ini(path: Path, section: str) -> tuple[str, ...] | None:
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(path, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError, OSError):
            return None
        if not cp.has_section(section):
            return None
        return tuple(cp.get(section, "testpaths", fallback="").split())

    if (repo_root / "pytest.ini").is_file():           # pytest uses pytest.ini even without a [pytest] section
        return ini(repo_root / "pytest.ini", "pytest") or ()
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib  # noqa: PLC0415
            opts = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("pytest", {}).get("ini_options")
        except (ImportError, ValueError, OSError):      # Python 3.10 has no TOML reader: the file name decides, as before
            opts = None
        if opts is not None:
            tp = opts.get("testpaths") or []
            return tuple(tp.split() if isinstance(tp, str) else tp)
    for name, section in (("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        if (repo_root / name).is_file():
            found = ini(repo_root / name, section)
            if found is not None:
                return found
    return ()


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
    if cpp_symbols.is_cxx_path(rel):
        return [(c.name, c.line) for c in cxx_cases(cpp_symbols.mask_source(text))[0]]
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


# ── C and C++ (ADR-DEVKB-008 §5, DKB-004) ───────────────────────────────────────────
# The one place a macro is tied to a framework (AD-8). `tier` is the TL's D3 ordering; `proof` is the include that
# must be present for the macro to count (None: the macro form is enough); `name` is how the case name is read.
CXX_FRAMEWORKS: dict[str, dict] = {
    "gtest": {"tier": 1, "macros": ("TEST", "TEST_F", "TEST_P", "TYPED_TEST", "TYPED_TEST_P"), "proof": None, "name": "suite.name"},
    "catch2": {"tier": 1, "macros": ("TEST_CASE", "SCENARIO", "TEMPLATE_TEST_CASE"), "proof": ("catch2/", "catch.hpp"), "name": "literal"},
    "doctest": {"tier": 1, "macros": ("TEST_CASE", "SCENARIO"), "proof": ("doctest/", "doctest.h"), "name": "literal"},
    "boost-test": {"tier": 2, "macros": ("BOOST_AUTO_TEST_CASE", "BOOST_FIXTURE_TEST_CASE", "BOOST_AUTO_TEST_CASE_TEMPLATE"),
                   "proof": None, "name": "first"},
    "unity": {"tier": 2, "macros": ("RUN_TEST",), "proof": ("unity.h",), "name": "run"},
    "ztest": {"tier": 2, "macros": ("ZTEST", "ZTEST_F", "ZTEST_USER", "ZTEST_USER_F", "ztest_unit_test"), "proof": ("ztest.h",),
              "name": "suite.name"},
}
_CXX_MACRO_NAMES = sorted({m for f in CXX_FRAMEWORKS.values() for m in f["macros"]}, key=len, reverse=True)
_CXX_RAW = re.compile(r"\b(?:" + "|".join(_CXX_MACRO_NAMES) + r")\b")
_CXX_MACRO = re.compile(r"\b(" + "|".join(_CXX_MACRO_NAMES) + r")\s*\(")


@dataclass
class CxxCase:
    name: str
    line: int
    framework: str
    macro: str
    body: bool       # a brace-bodied macro (the case is its own symbol); False: the case names a function


def _has_include(includes: list[str], proofs: tuple[str, ...]) -> bool:
    return any(p in inc if p.endswith("/") else inc.rsplit("/", 1)[-1] == p for inc in includes for p in proofs)


def cxx_cases(masked: cpp_symbols.Masked) -> tuple[list[CxxCase], int]:
    """(cases, number skipped as ambiguous) from one C/C++ file's masked text. Detection runs on masked text, so a
    macro in a comment, string or `#if 0` yields nothing. A macro two frameworks share (`TEST_CASE`) is assigned only
    when the file's includes prove exactly one; otherwise it is skipped and counted."""
    code, out, ambiguous = masked.code, [], 0
    for m in _CXX_MACRO.finditer(code):
        macro = m.group(1)
        o = m.end() - 1
        cl = cpp_symbols._match_close(code, o, "(", ")")
        if cl is None:
            continue
        args = cpp_symbols._split_top(code[o + 1:cl])
        line = masked.line(m.start())
        cands = [f for f, spec in CXX_FRAMEWORKS.items() if macro in spec["macros"]]
        ok = [f for f in cands if CXX_FRAMEWORKS[f]["proof"] is None or _has_include(masked.includes, CXX_FRAMEWORKS[f]["proof"])]
        if len(ok) != 1:
            if len(cands) > 1 and re.match(r"\s*\{", code[cl + 1:cl + 40]):
                ambiguous += 1
            continue
        fw = ok[0]
        kind = CXX_FRAMEWORKS[fw]["name"]
        if kind != "run" and macro != "ztest_unit_test" and not re.match(r"\s*\{", code[cl + 1:cl + 40]):
            continue                # a macro use that is not a case body
        if kind == "suite.name":
            if macro == "ztest_unit_test":
                fn = args[0].strip()
                if re.match(r"^\w+$", fn):
                    out.append(CxxCase(fn, _def_line(masked, fn) or line, fw, macro, False))
                continue
            if len(args) != 2 or not all(re.match(r"^\s*\w+\s*$", a) for a in args):
                continue
            out.append(CxxCase(f"{args[0].strip()}.{args[1].strip()}", line, fw, macro, True))
        elif kind == "first":
            if args and re.match(r"^\s*\w+\s*$", args[0]):
                out.append(CxxCase(args[0].strip(), line, fw, macro, True))
        elif kind == "literal":
            q = re.search(r"\"", code[o + 1:cl])
            lit = masked.literals.get(o + 1 + q.start()) if q else None
            if lit:
                out.append(CxxCase(lit, line, fw, macro, True))
        elif kind == "run":
            fn = args[0].strip() if args else ""
            if re.match(r"^\w+$", fn):
                out.append(CxxCase(fn, _def_line(masked, fn) or line, fw, macro, False))
    return out, ambiguous


def _def_line(masked: cpp_symbols.Masked, fn: str) -> int | None:
    m = re.search(r"(?m)^[ \t]*(?:static\s+|extern\s+)?(?:void|int)\s+" + re.escape(fn) + r"\s*\([^;{)]*\)\s*\{?", masked.code)
    return masked.line(m.start()) if m else None


def list_cxx_test_files(repo_root: Path) -> list[tuple[str, cpp_symbols.Masked, list[CxxCase], int]]:
    """Every tracked C/C++ file holding a test case: (path, masked text, cases, ambiguous count). A path named like a
    test is only a hint; a case needs the macro. Vendored and generated paths are skipped."""
    found = []
    for rel in cpp_symbols.list_files(repo_root):
        path = repo_root / rel
        try:
            if path.stat().st_size > cpp_symbols.MAX_FILE_BYTES:
                continue
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if not _CXX_RAW.search(text):
            continue
        masked = cpp_symbols.mask_source(text)
        cases, ambiguous = cxx_cases(masked)
        if cases or ambiguous:
            found.append((rel, masked, cases, ambiguous))
    return found
