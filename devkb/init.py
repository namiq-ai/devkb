"""`devkb init`: integrate devkb into a repository, idempotently, and take it out again.

  devkb init [--project .] [--toolset lean] [--hooks] [--claude-hook] [--no-build] [--dry-run]
  devkb init --remove [--project .]

Writes managed blocks, never whole files, so the repository's own content is untouched and re-running only refreshes
the block:

  AGENTS.md     when to use which devkb tool (read by Codex and most coding agents)
  CLAUDE.md     `@AGENTS.md`, so Claude Code reads the same instructions (one place to maintain)
  .mcp.json     the devkb MCP server, merged into any servers already declared
  .gitignore    .devkb/ (the graph is built locally, never committed)
  .claude/settings.json  with --claude-hook: a PreToolUse hook that gives Claude Code the file's pack at its first edit
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

AGENTS_BLOCK = """## devkb: ask the graph before you read or change code

This repository has a graph of its code in `.devkb/`: calls, tests, raised errors, commits, configuration. One call
returns what would take a dozen searches and file reads, and every item carries the line of code that proves it. The
graph does not hold *how the code is written*: to copy a pattern or learn a style, read the file.

**Choose by what you are about to do:**

**Instead of grep, to read code**: the graph holds every definition with its exact lines, so ask it rather than guess
`grep -A25`:
- `symbol(query)` (shell: `devkb symbol QUERY --source`): where a name is defined, with exact lines and the signature;
  `source=True` prints the body. A query can be a name, `Class.method`, `path::name`, a glob `parse_*`, `re:regex`, a
  prefix or a few words; a typo is tolerated, and below the confidence floor it says there is no match and suggests names.
- `outline(path)` (shell: `devkb outline PATH`): a file's symbols in order with line ranges, and its imports: look before you read.
- `uses(name)` (shell: `devkb uses NAME`): where a name, constant, module or key appears, grouped by the symbol that
  contains each use. Text matches, not resolved references.
- `search_docs(query)` (shell: `devkb docs QUERY`): what the documentation says, with the heading of each hit.
A symbol in a language that stores no end line (TypeScript, JavaScript) is reported as "end unknown": read from its start.


| You are about to... | Use | You get |
|---|---|---|
| open a file to see what depends on it, or edit it | `pack(kind="file", subject=PATH)` (shell: `devkb pack --project . file PATH`) | the functions other files call, the files that depend on it, the tests to run |
| change a function's behaviour or signature | `pack(kind="change", subject=NAME, path=PATH)` (shell: `devkb pack --project . refactor NAME`) | callers at any depth, tests among them |
| start from an error message or a failing request | `pack(kind="error", subject="MESSAGE")` | what raises it, the handlers that reach it |
| find who calls one function directly | search with grep | one hop: a pack adds a step and saves nothing |
| learn how a pattern is written, to copy it | read the file | the graph does not store this |
| decide which tests to run | `tests_to_run` or `tests_for` | the tests, ranked |
| review a commit or a diff | `review_pack` | changed functions, outside callers, untested changes |
| find a setting or a service | `config` | where it is declared and read |

**How to work:**
1. Ask first, read second. Run the pack for a file before you read it to judge impact and before your first edit of it.
   In Claude Code the devkb hook also adds that pack to your first Edit or Write of each file; read it, then continue.
2. A pack marked **Complete** is the whole answer: do not search again to check it. If it is Incomplete, search only the
   files it names. If it says files changed since the graph was built, re-read those files.
3. After editing, run the tests the pack named first, then the full suite. If you edited many files, rebuild first:
   `devkb build --project .` (a few seconds on most repositories)."""


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


def _unpaired(text: str, begin: str, end: str) -> int | None:
    """The line of the first marker without its partner, or None. A BEGIN whose END was deleted by hand would make the
    block regex run on to the next END and take the user's text between them with it (#50)."""
    marks = sorted([(m.start(), begin) for m in re.finditer(re.escape(begin), text)]
                   + [(m.start(), end) for m in re.finditer(re.escape(end), text)])
    for i, (pos, kind) in enumerate(marks):
        partner = marks[i + 1][1] if i + 1 < len(marks) else None
        if (i % 2 == 0 and (kind != begin or partner != end)) or (i % 2 == 1 and kind != end):
            return text.count("\n", 0, pos) + 1
    return None


def _refuse_unpaired(root: Path, files: dict[str, tuple[str, str, str]]) -> None:
    """Fail closed before anything is written: a file whose managed markers do not pair up is not touched."""
    for rel, (text, begin, end) in files.items():
        line = _unpaired(text, begin, end)
        if line is not None:
            raise SystemExit(f"{root / rel}, line {line}: a devkb block marker has no partner, so devkb init "
                             f"changed nothing. Restore or delete the marker by hand, then run it again")


class Plan:
    def __init__(self, root: Path, dry_run: bool) -> None:
        self.root, self.dry_run, self.changes = root, dry_run, []

    def write(self, rel: str, text: str | None) -> None:
        path = self.root / rel
        old = _read(path, newline="") if path.exists() else None
        if text is not None and not text.strip():
            text = None
        eol = "\r\n" if old and "\r\n" in old.split("\n", 1)[0] + "\n" else "\n"  # the file's first line ending (#52)
        if text is not None:
            text = text.replace("\n", eol)
        if old == text:
            return
        self.changes.append(f"{'remove' if text is None else 'create' if old is None else 'update'} {rel}")
        if self.dry_run:
            return
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, newline="")


def _read(path: Path, newline: str | None = None) -> str:
    """The file's text, "" when absent; newline="" keeps its line endings as they are (Path.read_text has no newline
    argument before Python 3.13)."""
    if not path.exists():
        return ""
    with path.open(newline=newline) as f:
        return f.read()


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


HOOK_COMMAND = "devkb hook pre-edit"


def _settings(root: Path, install: bool) -> str | None:
    """`.claude/settings.json` with a PreToolUse hook that gives the agent the file's pack at its first edit; other
    settings and hooks are kept, and removing devkb removes only this entry."""
    path = root / ".claude" / "settings.json"
    try:
        cfg = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        raise SystemExit(f"{path} is not valid JSON; fix it or add the devkb hook by hand")
    groups = cfg.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for g in groups:
        g["hooks"] = [h for h in g.get("hooks", []) if HOOK_COMMAND not in h.get("command", "")]
    groups[:] = [g for g in groups if g.get("hooks")]
    if install:
        groups.append({"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
                       "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 30}]})
    if not groups:
        cfg["hooks"].pop("PreToolUse")
    if not cfg["hooks"]:
        cfg.pop("hooks")
    return json.dumps(cfg, indent=2) + "\n" if cfg else None


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


def run(root: Path, toolset: str | None, hooks: bool, dry_run: bool, claude_hook: bool = False) -> list[str]:
    """toolset None removes devkb. Returns the changes made (or planned, with dry_run)."""
    p = Plan(root, dry_run)
    install = toolset is not None
    agents, claude, ignore = _read(root / "AGENTS.md"), _read(root / "CLAUDE.md"), _read(root / ".gitignore")
    hdir = _hooks_dir(root)
    _refuse_unpaired(root, {"AGENTS.md": (agents, BEGIN, END), "CLAUDE.md": (claude, BEGIN, END),
                            ".gitignore": (ignore, HASH_BEGIN, HASH_END),
                            **{str(hdir / n): (_read(hdir / n), HASH_BEGIN, HASH_END) for n in HOOKS}})
    p.write("AGENTS.md", _set_block(agents, AGENTS_BLOCK) if install else _drop_block(agents))
    if (root / "CLAUDE.md").resolve() != (root / "AGENTS.md").resolve():  # one file under two names: block once (#51)
        p.write("CLAUDE.md", _set_block(claude, "@AGENTS.md") if install else _drop_block(claude))
    p.write(".gitignore", _set_block(ignore, ".devkb/", HASH_BEGIN, HASH_END) if install else _drop_block(ignore, HASH_BEGIN, HASH_END))
    p.write(".mcp.json", _mcp(root, toolset))
    if claude_hook or not install:
        p.write(".claude/settings.json", _settings(root, install))
    for name in HOOKS:
        path = hdir / name
        if not install or hooks:
            before = len(p.changes)
            p.write(str(path), _hook(_read(path), install))  # an absolute path joins as itself (worktrees)
            if install and len(p.changes) > before and not dry_run:
                path.chmod(0o755)
    return p.changes


def server_command_problem() -> str | None:
    """Why agents could not start the `devkb` command that `.mcp.json` names, or None. Claude Code, Cursor and Codex
    start it from the user's normal PATH, so a devkb installed only inside a virtual environment never starts and the
    agent silently has no devkb tools (found dogfooding, 2026-11-15)."""
    import shutil  # noqa: PLC0415
    import sys  # noqa: PLC0415
    found = shutil.which("devkb")
    fix = 'install it as a tool so it is on your PATH everywhere: `uv tool install "devkb[mcp]"` (or `pipx install "devkb[mcp]"`)'
    if found is None:
        return f"the `devkb` command is not on your PATH, so agents cannot start the devkb server; {fix}"
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    # The directory on PATH decides, not where the command's symlink leads: `uv tool install` and pipx put a shim on
    # PATH that resolves into the tool's own venv, which is where init then runs from (#73).
    if in_venv and Path(found).parent.resolve().is_relative_to(Path(sys.prefix).resolve()):
        return (f"`devkb` is only on the PATH of this virtual environment ({sys.prefix}); agents start it from your "
                f"normal PATH and will not find it; {fix}")
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="devkb init", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--toolset", default="lean-pack", help="the MCP toolset agents get (lean-pack, lean, dev, core, workflow, all)")
    ap.add_argument("--hooks", action="store_true", help="rebuild the graph after commits, merges and checkouts")
    ap.add_argument("--claude-hook", action="store_true", help="give Claude Code the file's pack at its first Edit or Write (.claude/settings.json)")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--remove", action="store_true", help="take devkb out of the repository again")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.project).resolve()
    changes = run(root, None if a.remove else a.toolset, a.hooks, a.dry_run, a.claude_hook)
    print(("would " if a.dry_run else "") + ("\n".join(changes) if changes else "nothing to change"))
    problem = None if a.remove else server_command_problem()
    if problem:
        print(f"WARNING: {problem}", file=sys.stderr)
    if not (a.remove or a.no_build or a.dry_run):
        from devkb import cli  # noqa: PLC0415
        return cli.main(["build", "--project", str(root)])
    if not a.remove and not a.dry_run:
        print(f"next: devkb build --project {a.project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
