"""Where a project lives and how it is laid out, for every devkb tool.

devkb works on any git repository. A project is named either by a path (`--project .` or
`--project /path/to/repo`) or by a code listed in an optional registry (`DEVKB_REGISTRY`, a JSON file
`{"projects": [{"code": "APP", "repo": "/path"}]}`). Its layout comes from `devkb.json` at the repository
root, or from `pms.config.json` when a project already has one; both are optional, and every path has a
default, so a bare repository works with no configuration at all.

devkb.json (every key optional):

    {"code": "APP", "ticket_prefix": "APP",
     "paths": {"issues_dir": "issues", "spec_dirs": ["docs", "docs/adr"], "frontend_src": "web/src",
               "frontend_kind": "nextjs", "sprint_dir": "sprints", "board_file": "BOARD.md"},
     "role_profiles": {"BE": "roles/backend.md"}, "roles_dir": "roles", "graph": {"members": []},
     "run_repo_scripts": false}

`run_repo_scripts` must be true before devkb imports or runs any script that lives in the analysed
repository (a readiness gate, a compliance monitor). It is off by default: analysing a repository must
never execute its code.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILES = ("devkb.json", "pms.config.json")
PROJECTS_JSON = Path(os.environ["DEVKB_REGISTRY"]) if os.environ.get("DEVKB_REGISTRY") else None


def load_config(repo_root: Path) -> dict:
    """The project's devkb configuration: devkb.json, else pms.config.json, else {}."""
    for name in CONFIG_FILES:
        cfg = _read_json(Path(repo_root) / name)
        if isinstance(cfg, dict):
            return cfg
    return {}


def run_repo_scripts(repo_root: Path) -> bool:
    return bool(load_config(repo_root).get("run_repo_scripts")) or os.environ.get("DEVKB_RUN_REPO_SCRIPTS") == "1"


@dataclass(frozen=True)
class ProjectContext:
    code: str
    repo_root: Path
    ticket_prefix: str
    issues_dir: Path
    tests_dir: Path
    sprint_dir: Path
    devkb_dir: Path
    board_file: Path
    wp_map_file: Path
    # Where the project's frontend is and which extractor reads it; defaulted so callers that only need
    # tickets and paths can construct a context without it.
    frontend_src: Path | None = None
    frontend_kind: str = "nextjs"
    # ODSF-102. Where THIS project keeps the documents that specify it, relative
    # to its own root. `spec_docs.py` used to hardcode four globs, so a project
    # keeping specs anywhere else was invisible to its own BA: ODSF's whole
    # specification set lives under `backlogs/` and its graph carried 2 Spec
    # nodes, while OCO -- whose layout happens to match those globs -- carried
    # 187. Empty means "use the defaults", so a project that declares nothing is
    # byte-identical to before: this is opt-in, not a re-shaping of every graph.
    # Defaulted for the same reason frontend_src above is -- ProjectContext is
    # constructed directly by tests and by callers with no opinion about specs.
    spec_dirs: tuple[str, ...] = ()


# Exactly the roots spec_docs.py scanned before this was configurable, with
# their original recursion: a trailing `/**` means "and subdirectories", its
# absence means top level only. `design` was the only recursive one, and
# `docs/adr`'s siblings under `docs/` were deliberately excluded -- keeping the
# distinction is what makes "a project that declares nothing is unchanged" true
# rather than nearly true.
#
# ODSF-103 adds `docs` — top level only, NOT `docs/**`. The subdirectories under
# `docs/` are per-owner working areas (compliance evidence, process diagrams,
# requirement templates) and are not specifications of the system; `docs/adr/`
# is already covered by its own entry. A project's consolidated
# requirement/technical/test documents DO live at that top level, and were
# reachable only as `File` nodes, so a context bundle could not surface the
# document that answers the question it was asked. Widening the DEFAULT rather
# than leaving it to each project's declaration: `docs/` is a universal
# convention, and a project that disagrees can now say so (ODSF-102).
#
# ODSF-128 adds `docs/spec` — top level only, for the same reason `docs` is:
# it is where ADR-SDP-SPEC-001 puts generated-then-curated specifications, and
# `docs` above is deliberately non-recursive so it does not reach a
# subdirectory. Every project gets it in the default rather than each having to
# declare it, because the folder contract is the platform's, not one project's.
DEFAULT_SPEC_DIRS: tuple[str, ...] = ("docs/adr", "docs", "docs/spec", "design/**", ".onboarding")


def safe_spec_dirs(declared: Any, default: tuple[str, ...] = DEFAULT_SPEC_DIRS) -> tuple[str, ...]:
    """Validate a project's declared spec roots.

    This value comes out of a config file and is then used to walk the
    filesystem, so an entry that escapes the project is refused rather than
    resolved: `../../etc`, an absolute path, or a `~` are dropped. A
    non-list, or a list with nothing usable left in it, falls back to the
    default -- a malformed declaration must not silently produce an empty
    corpus, which would look exactly like a project with no specifications.
    """
    if not isinstance(declared, list):
        return default
    out: list[str] = []
    for entry in declared:
        if not isinstance(entry, str):
            continue
        raw = entry.strip()
        # Tested BEFORE the trailing slash is trimmed: stripping first turned
        # "/etc" into "etc", which is not a refusal but a silent reinterpretation
        # as <repo>/etc -- a different directory than the one declared, quietly
        # substituted. Refusing is the only honest answer to a root this code
        # cannot honour.
        if not raw or raw.startswith(("/", "~")) or ".." in Path(raw).parts:
            continue
        rel = raw.strip("/")
        if rel:
            out.append(rel)
    return tuple(dict.fromkeys(out)) or default


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def external_context(code: str, repo_root: Path, devkb_dir: Path) -> ProjectContext:
    """A context for a repository outside the factory registry: a public project in a benchmark (ODSF-315). It is
    never a fallback of `resolve()`, which keeps refusing an unregistered code; a caller asks for it explicitly, and
    such a repository has no tickets, board or role profiles, so those paths simply do not exist."""
    root = Path(repo_root).resolve()
    return ProjectContext(code=code, repo_root=root, ticket_prefix=f"{code}-EXT", issues_dir=root / "issues",
                          tests_dir=root / "tests", sprint_dir=root / "sprints", devkb_dir=Path(devkb_dir),
                          board_file=root / "PROJECT_BOARD.md", wp_map_file=root / "wp-map.json")


def registry() -> list[dict]:
    if PROJECTS_JSON is None:
        return []
    return (_read_json(PROJECTS_JSON, {}) or {}).get("projects", [])


def _from_root(code: str | None, repo_root: Path) -> ProjectContext:
    cfg = load_config(repo_root)
    project = cfg.get("project") if isinstance(cfg.get("project"), dict) else {}
    code = code or cfg.get("code") or project.get("code") or repo_root.name.upper()
    ticket_prefix = cfg.get("ticket_prefix") or project.get("code") or code
    paths = cfg.get("paths", {}) if isinstance(cfg.get("paths"), dict) else {}
    issues_rel = paths.get("issues_dir") or "issues"
    sprint_rel = paths.get("sprint_dir") or "historical/sprints"
    board_rel = paths.get("board_file") or "sdp/data/PROJECT_BOARD.md"
    wp_map_rel = paths.get("orchestrator_wp_map") or "sdp/data/orchestrator/wp-map.json"
    return ProjectContext(
        code=code,
        repo_root=repo_root,
        ticket_prefix=ticket_prefix,
        issues_dir=repo_root / issues_rel,
        tests_dir=repo_root / "tests",
        sprint_dir=repo_root / sprint_rel,
        devkb_dir=Path(os.environ["DEVKB_DIR"]) if os.environ.get("DEVKB_DIR") else repo_root / ".devkb",
        board_file=repo_root / board_rel,
        wp_map_file=repo_root / wp_map_rel,
        frontend_src=(repo_root / paths["frontend_src"]) if paths.get("frontend_src") else None,
        frontend_kind=paths.get("frontend_kind") or "nextjs",
        spec_dirs=safe_spec_dirs(paths.get("spec_dirs")),
    )


def resolve(code: str) -> ProjectContext:
    """`code` is a path to a repository, a code in the registry, or a code matching DEVKB_REPO's
    configuration. Raises ValueError when none applies: devkb refuses to guess which repository is meant."""
    as_path = Path(code).expanduser()
    if as_path.is_dir() and (as_path / ".git").exists() or code in (".", "..") or "/" in code:
        if not as_path.is_dir():
            raise ValueError(f"{code!r} is not a directory")
        return _from_root(None, as_path.resolve())
    entry = next((p for p in registry() if p.get("code") == code), None)
    if entry is not None:
        return _from_root(code, Path(entry["repo"]).resolve())
    if os.environ.get("DEVKB_REPO"):
        return _from_root(code, Path(os.environ["DEVKB_REPO"]).resolve())
    raise ValueError(f"{code!r} is neither a repository path nor a registered project "
                     "(pass --project PATH, set DEVKB_REPO, or list it in DEVKB_REGISTRY)")
