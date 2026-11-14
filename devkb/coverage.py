#!/usr/bin/env python3
"""How much of a project the devkb graph actually holds (ODSF-304).

A graph is only as trustworthy as its coverage, and the gap was invisible:
One project's graph reported 15,002 nodes for 229 KLOC and nothing said that 94% of
its test functions and every JavaScript and template file were missing. This
compares what git tracks with what the graph holds, per category, and fails a
category below its floor.

Usage:
  python3 devkb/coverage.py --project .            # report
  python3 devkb/coverage.py --project . --check    # exit 1 below any floor
  python3 devkb/coverage.py --project . --json

Floors default to DEFAULT_FLOORS and are overridden per project in
`pms.config.json` under `devkb.coverage_floors`. A category with fewer than
MIN_POPULATION items in the repo is reported but never fails: a project with
three markdown files has no meaningful specification ratio.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.project_context import ProjectContext, load_config, resolve  # noqa: E402
from devkb.test_discovery import list_test_files, tests_in_file  # noqa: E402

DEFAULT_FLOORS = {
    "test_functions": 0.9,
    "python_files": 0.9,
    "script_files": 0.9,
    "template_files": 0.9,
    "spec_documents": 0.5,
    "ticket_files": 0.9,
}
MIN_POPULATION = 10

_SCRIPT_SKIP = re.compile(
    r"(\.min\.js$|\.test\.[cm]?[jt]sx?$|\.spec\.[cm]?[jt]sx?$|\.d\.ts$|\.config\.[cm]?[jt]s$|(^|/)fixtures?/"
    r"|(^|/)(lib|libs|vendor|node_modules|output|dist|build|\.impl-worktrees|\.claude)/)")
# Markdown that is not a specification: tickets, run output, generated reports.
_DOC_SKIP = re.compile(
    r"(^|/)(issues|historical|output|logs|runtime|node_modules|\.impl-worktrees|\.claude|\.onboarding"
    r"|_bmad-output|sprints|archive|\.agents?)/|(^|/)(README|CHANGELOG|INDEX)\.md$", re.IGNORECASE)


def _tracked(repo_root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "--recurse-submodules"], cwd=repo_root, capture_output=True, text=True, check=False).stdout
    return [f for f in out.splitlines() if f]


def _load_nodes(ctx: ProjectContext) -> list[dict]:
    path = ctx.devkb_dir / "nodes.jsonl"
    if not path.exists():
        raise SystemExit(f"no graph at {path}; run: python3 devkb/build.py --project {ctx.code}")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _floors(ctx: ProjectContext) -> dict[str, float]:
    floors = dict(DEFAULT_FLOORS)
    try:
        cfg = load_config(ctx.repo_root)
        floors.update({k: float(v) for k, v in (cfg.get("devkb", {}).get("coverage_floors") or {}).items()})
    except (OSError, ValueError):
        pass
    return floors


def _row(name: str, covered: int, population: int, floors: dict[str, float], note: str = "") -> dict:
    ratio = covered / population if population else 1.0
    floor = floors[name]
    return {
        "category": name, "covered": covered, "population": population,
        "ratio": round(ratio, 4), "floor": floor, "note": note,
        "enforced": population >= MIN_POPULATION,
        "ok": population < MIN_POPULATION or ratio >= floor,
    }


def measure(ctx: ProjectContext) -> list[dict]:
    nodes = _load_nodes(ctx)
    floors = _floors(ctx)
    tracked = _tracked(ctx.repo_root)
    rows: list[dict] = []

    # Test functions: every function discovery finds against TestCase nodes.
    test_keys = {n["natural_key"] for n in nodes if n["type"] == "TestCase"}
    found = 0
    held = 0
    for rel in list_test_files(ctx.repo_root):
        for _name, line in tests_in_file(ctx.repo_root, rel):
            found += 1
            held += f"{rel}:{line}" in test_keys
    rows.append(_row("test_functions", held, found, floors))

    symbol_files = {n["natural_key"].split("::", 1)[0] for n in nodes if n["type"] == "Symbol"}

    def files_with_symbols(paths: list[str]) -> int:
        return sum(1 for p in paths if p in symbol_files)

    py = [f for f in tracked if f.endswith(".py")
          and not re.search(r"(^|/)(test_[^/]+|[^/]+_test|conftest|__init__)\.py$", f)
          and not _SCRIPT_SKIP.search(f)
          and (ctx.repo_root / f).is_file() and (ctx.repo_root / f).stat().st_size > 0]
    rows.append(_row("python_files", files_with_symbols(py), len(py), floors,
                     "non-test .py files that define at least one symbol"))

    scripts = [f for f in tracked if re.search(r"\.(tsx?|[cm]?js)$", f) and not _SCRIPT_SKIP.search(f)]
    rows.append(_row("script_files", files_with_symbols(scripts), len(scripts), floors, "TypeScript and JavaScript"))

    xml = [f for f in tracked if f.endswith(".xml")
           and re.search(r"(<template\b|<menuitem\b|t-name=|model=\"ir\.(ui\.view|actions\.|cron)|model=\"res\.groups)",
                         (ctx.repo_root / f).read_text(errors="replace") if (ctx.repo_root / f).is_file() else "")]
    rows.append(_row("template_files", files_with_symbols(xml), len(xml), floors, "Odoo XML that declares templates, views, actions or menus"))

    spec_paths = {n["natural_key"] for n in nodes if n["type"] == "Spec"}
    docs = [f for f in tracked if f.endswith(".md") and not _DOC_SKIP.search(f)]
    rows.append(_row("spec_documents", sum(1 for d in docs if d in spec_paths), len(docs), floors,
                     "markdown outside issues, history, output and generated folders"))

    issues_rel = ctx.issues_dir.relative_to(ctx.repo_root).as_posix() if ctx.issues_dir.is_relative_to(ctx.repo_root) else "issues"
    issue_files = [f for f in tracked if f.startswith(issues_rel + "/") and f.endswith(".md") and not f.endswith("README.md")]
    ticket_ids = {n["natural_key"] for n in nodes if n["type"] == "Ticket"}
    held_tickets = sum(1 for f in issue_files if Path(f).name.split("_", 1)[0] in ticket_ids)
    rows.append(_row("ticket_files", held_tickets, len(issue_files), floors))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="devkb graph coverage against what git tracks")
    ap.add_argument("--project", required=True)
    ap.add_argument("--check", action="store_true", help="exit 1 when any enforced category is below its floor")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = measure(resolve(args.project))
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"devkb coverage ({args.project})")
        for r in rows:
            mark = "ok  " if r["ok"] else "FAIL"
            enforced = "" if r["enforced"] else "  (not enforced: fewer than %d)" % MIN_POPULATION
            print(f"  {mark} {r['category']:<16} {r['covered']:>6} / {r['population']:<6} "
                  f"{r['ratio']:>6.1%}  floor {r['floor']:.0%}{enforced}  {r['note']}")
    return 1 if args.check and any(not r["ok"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
