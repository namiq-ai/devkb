"""`devkb`: one command for every devkb tool.

  devkb build   --project .                 build the graph (symbols, then process) into .devkb/
  devkb pack    --project . refactor NAME   a pre-computed context pack (error | change | refactor)
  devkb query   --project . --about ID      the graph's answer about a ticket, file or symbol
  devkb mcp     --project . [--toolset lean] serve the graph to an agent over MCP (stdio)
  devkb audit   --project .                 per-relation counts, fan-out and cost of the graph
  devkb coverage --project .                what share of the repository the graph covers

`--project` takes a repository path (or a code listed in DEVKB_REGISTRY). See devkb/project_context.py.
"""
from __future__ import annotations

import runpy
import sys

COMMANDS = {
    "pack": "devkb.packs",
    "query": "devkb.query",
    "mcp": "devkb.mcp_server",
    "audit": "devkb.audit",
    "coverage": "devkb.coverage",
    "startup": "devkb.startup",
}


def _run(module: str, argv: list[str]) -> int:
    sys.argv = [module, *argv]
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        return int(exc.code or 0) if not isinstance(exc.code, str) else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "build":
        return _run("devkb.build_symbols", rest) or _run("devkb.build", rest)
    if cmd not in COMMANDS:
        print(f"devkb: unknown command {cmd!r}\n{__doc__}", file=sys.stderr)
        return 2
    return _run(COMMANDS[cmd], rest)


if __name__ == "__main__":
    raise SystemExit(main())
