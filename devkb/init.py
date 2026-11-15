"""`devkb init`: integrate devkb into a repository, idempotently, and take it out again.

  devkb init [--project .] [--toolset lean] [--hooks] [--no-build] [--dry-run]
  devkb init --remove [--project .]

Writes managed blocks, never whole files, so the repository's own content is untouched and re-running only refreshes
the block:

  AGENTS.md     when to use which devkb tool (read by Codex and most coding agents)
  CLAUDE.md     `@AGENTS.md`, so Claude Code reads the same instructions (one place to maintain)
  .mcp.json     the devkb MCP server, merged into any servers already declared
  .gitignore    .devkb/ (the graph is built locally, never committed)
  git hooks     with --hooks: rebuild the graph in the background after a commit, merge or checkout

Why instructions and not only a server: in the study, agents left to choose used the graph in 88% of runs that
followed a call chain and in none of the requirement, solution or review runs. The savings were measured with these
instructions in place.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BEGIN, END = "<!-- devkb:begin (managed by `devkb init`; edit outside this block) -->", "<!-- devkb:end -->"
HASH_BEGIN, HASH_END = "# devkb:begin (managed by `devkb init`)", "# devkb:end"
HOOKS = ("post-commit", "post-merge", "post-checkout")

AGENTS_BLOCK = """## devkb: before you change code

This repository has a graph of its code (calls, tests, raised errors, commits, configuration) in `.devkb/`. Use it at
these steps; each command prints the answer with the line of code that proves every item and says what it could not
see:

1. **Before you edit an existing file**, run `devkb pack --project . file PATH`: which of its functions other files
   call (your change must keep them working), the files that depend on it, and the tests that exercise it.
2. **Before you change a function's signature or behaviour**, run `devkb pack --project . refactor NAME` (every
   caller, tests among them) or `devkb pack --project . change NAME --path PATH` (callers at any depth, tests to run).
3. **When you start from an error message**, run `devkb pack --project . error "MESSAGE"`.
4. **After editing**, run the tests the pack named first, then the full suite.
5. If you edited many files, rebuild first: `devkb build --project .` (a few seconds on most repositories).

The same graph is served by the `devkb` MCP server for questions in between:

| Question | Use |
|---|---|
| An area you have not read: its files, key functions, tests, docs | `explain_area` with the folder |
| Where a new feature or change belongs: related code, docs, tests | `feature_brief` with the goal |
| Code that does something, found by what it does | `find_code` |
| Who calls a function / the impact of a change | `callers` / `impact` |
| Which tests to run | `tests_to_run`, or `tests_for` a file or function |
| A commit or a diff to review | `review_pack` |
| A setting or a service | `config` |

Rules: a pack or answer marked **Complete** is the whole answer: do not search again. If it is incomplete, search only
the files it names. If it says files changed since the graph was built, re-read those files."""


def _between(text: str, begin: str, end: str) -> re.Pattern:
    return re.compile(rf"\n?{re.escape(begin)}.*?{re.escape(end)}\n?", re.S)


def _set_block(text: str, body: str, begin: str = BEGIN, end: str = END) -> str:
    block = f"{begin}\n{body}\n{end}\n"
    rx = _between(text, begin, end)
    if rx.search(text):
        return rx.sub(lambda _m: "\n" + block if _m.group(0).startswith("\n") else block, text, count=1)
    sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + block


def _drop_block(text: str, begin: str = BEGIN, end: str = END) -> str:
    return _between(text, begin, end).sub("\n", text, count=1).strip("\n") + "\n" if begin in text else text


class Plan:
    def __init__(self, root: Path, dry_run: bool) -> None:
        self.root, self.dry_run, self.changes = root, dry_run, []

    def write(self, rel: str, text: str | None) -> None:
        path = self.root / rel
        old = path.read_text() if path.exists() else None
        if text is not None and not text.strip():
            text = None
        if old == text:
            return
        self.changes.append(f"{'remove' if text is None else 'create' if old is None else 'update'} {rel}")
        if self.dry_run:
            return
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _mcp(root: Path, toolset: str | None) -> str | None:
    path = root / ".mcp.json"
    try:
        cfg = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        raise SystemExit(f"{path} is not valid JSON; fix it or add the devkb server by hand")
    servers = cfg.setdefault("mcpServers", {})
    if toolset is None:
        servers.pop("devkb", None)
        if not servers:
            cfg.pop("mcpServers")
        return json.dumps(cfg, indent=2) + "\n" if cfg else None
    servers["devkb"] = {"command": "devkb", "args": ["mcp", "--project", ".", "--toolset", toolset]}
    return json.dumps(cfg, indent=2) + "\n"


def _hooks_dir(root: Path) -> Path:
    out = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"{root} is not a git repository")
    return (root / out.stdout.strip()).resolve()


def _hook(text: str, install: bool) -> str | None:
    body = "( devkb build --project \"$(git rev-parse --show-toplevel)\" > /dev/null 2>&1 & )"
    if install:
        return _set_block(text or "#!/bin/sh\n", body, HASH_BEGIN, HASH_END)
    out = _drop_block(text, HASH_BEGIN, HASH_END)
    return None if out.strip() in ("", "#!/bin/sh") else out


def run(root: Path, toolset: str | None, hooks: bool, dry_run: bool) -> list[str]:
    """toolset None removes devkb. Returns the changes made (or planned, with dry_run)."""
    p = Plan(root, dry_run)
    install = toolset is not None
    agents, claude, ignore = _read(root / "AGENTS.md"), _read(root / "CLAUDE.md"), _read(root / ".gitignore")
    p.write("AGENTS.md", _set_block(agents, AGENTS_BLOCK) if install else _drop_block(agents))
    p.write("CLAUDE.md", _set_block(claude, "@AGENTS.md") if install else _drop_block(claude))
    p.write(".gitignore", _set_block(ignore, ".devkb/", HASH_BEGIN, HASH_END) if install else _drop_block(ignore, HASH_BEGIN, HASH_END))
    p.write(".mcp.json", _mcp(root, toolset))
    hdir = _hooks_dir(root)
    for name in HOOKS:
        path = hdir / name
        if not install or hooks:
            before = len(p.changes)
            p.write(str(path), _hook(_read(path), install))  # an absolute path joins as itself (worktrees)
            if install and len(p.changes) > before and not dry_run:
                path.chmod(0o755)
    return p.changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="devkb init", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--toolset", default="dev", help="the MCP toolset agents get (dev, lean, core, workflow, all)")
    ap.add_argument("--hooks", action="store_true", help="rebuild the graph after commits, merges and checkouts")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--remove", action="store_true", help="take devkb out of the repository again")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.project).resolve()
    changes = run(root, None if a.remove else a.toolset, a.hooks, a.dry_run)
    print(("would " if a.dry_run else "") + ("\n".join(changes) if changes else "nothing to change"))
    if not (a.remove or a.no_build or a.dry_run):
        from devkb import cli  # noqa: PLC0415
        return cli.main(["build", "--project", str(root)])
    if not a.remove and not a.dry_run:
        print(f"next: devkb build --project {a.project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
