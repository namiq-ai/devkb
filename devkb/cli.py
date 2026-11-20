"""`devkb`: one command for every devkb tool.

  devkb init    [--hooks] [--remove]        integrate devkb into this repository (AGENTS.md, CLAUDE.md, .mcp.json)
  devkb build   --project .                 build the graph (symbols, then process) into .devkb/
  devkb pack    --project . refactor NAME   a pre-computed context pack (error | change | refactor)
  devkb query   --project . --about ID      the graph's answer about a ticket, file or symbol
  devkb mcp     --project . [--toolset lean] serve the graph to an agent over MCP (stdio)
  devkb audit   --project .                 per-relation counts, fan-out and cost of the graph
  devkb coverage --project .                what share of the repository the graph covers
  devkb symbol|outline|uses|docs QUERY      read tools: a definition and its body, a file's outline, where a name is used, what the docs say
  devkb misses  --project .                 graph misses grep found, as ticket drafts to review and file (#133)
  devkb stats   --project .                 calls by tool and outcome: complete, incomplete, ambiguous, ... (#151)
  devkb guardrail-stats                     the guardrail's substitutions, pass-throughs and repeats (#149)
  devkb hook    pre-edit                   Claude Code hook: the file's pack, given to the agent at its first edit

`--project` takes a repository path (or a code listed in DEVKB_REGISTRY). See devkb/project_context.py.
"""
from __future__ import annotations

import runpy
import sys

COMMANDS = {
    "init": "devkb.init",
    "pack": "devkb.packs",
    "query": "devkb.query",
    "mcp": "devkb.mcp_server",
    "audit": "devkb.audit",
    "coverage": "devkb.coverage",
    "startup": "devkb.startup",
    "hook": "devkb.hook",
    "misses": "devkb.misses",
    "stats": "devkb.outcomes",
}


def _run(module: str, argv: list[str]) -> int:
    sys.argv = [module, *argv]
    from devkb.service import GraphNotBuilt
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        if isinstance(exc.code, str):           # a message: print it, as Python itself would have (#99)
            print(exc.code, file=sys.stderr)
            return 1
        return int(exc.code or 0)
    except GraphNotBuilt as exc:                # one line that says what to do, never a traceback (#212)
        print(f"devkb: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "build":  # one at a time, and a line in .devkb/build.log (#158)
        from devkb.buildlog import logged_build  # noqa: PLC0415
        return logged_build(rest)
    if cmd == "build-direct":
        return _run("devkb.build_symbols", rest) or _run("devkb.build", rest)
    if cmd in ("symbol", "outline", "uses", "docs"):
        return _run("devkb.read_tools", [cmd, *rest])
    if cmd == "guardrail-stats":
        return _run("devkb.outcomes", ["--guardrail", *rest])
    if cmd not in COMMANDS:
        print(f"devkb: unknown command {cmd!r}\n{__doc__}", file=sys.stderr)
        return 2
    return _run(COMMANDS[cmd], rest)


if __name__ == "__main__":
    raise SystemExit(main())
