# QB3 baseline: does a release audit flag what breaks a user? (2026-11-21)

Design: `docs/specs/quality-benchmarks.md`. Tool: `bench/quality/qb3_release.py`. No graph and no model runs.

## Setup
17 tags (v0.1.0 to v0.2.14), 16 consecutive intervals. **Oracle:** the public surface at each tag, read with `ast` from `git show
TAG:path`, independent of the graph: the `devkb <command>` lines of `cli.py`'s docstring and its `COMMANDS` table; every `--flag` any
module passes to `add_argument`; the MCP tool names in `mcp_server.py`'s module-level lists; `model.NODE_TYPES` and `model.VERBS`. An
item that disappeared between two tags is *breaking*, one that appeared *additive*, no change *internal*. Baselines: the commit
subjects (a conventional-commit `!`, "BREAKING", "remove", "rename", "drop", "deprecate" mean breaking; `feat` or "add" additive) and
the file list (any of `cli.py`, `mcp_server.py`, `model.py`, `init.py`, `hook.py` touched).

## Result
| | intervals |
|---|---|
| oracle: breaking | **0** |
| oracle: additive | 3 (v0.2.6 to v0.2.7: 16 items added; v0.2.7 to v0.2.8: 1; v0.2.11 to v0.2.12: 5) |
| oracle: internal | 13 |

| method | calls "breaking" | of which right | verdict accuracy | misses (oracle breaking, not flagged) |
|---|---|---|---|---|
| commit subjects | 6 | 0 | 0.50 | 0 (there are none) |
| file list | 10 | 0 | 0.38 | 0 (there are none) |

## Reading
- **Breaking-change recall cannot be measured here.** In 16 releases no command, flag, tool, node type or edge verb was removed. There
  is no positive to find. A benchmark of "does the audit catch breaking changes" needs a history that has some.
- **What the baselines get wrong is false alarms.** The subject heuristic calls 6 of 16 releases breaking (words such as "remove" in a
  commit about something internal) and the file-list heuristic 10 of 16 (these files change in most releases). None was right. For
  this repository, a release audit's value is *quiet when nothing public changed*, which is a precision problem.
- **The oracle is itself a release audit and needs no graph:** about 100 lines of `ast` over the files at two tags give the exact
  removed and added public items, and found the three additive releases. For a repository whose public surface is a CLI, a tool list
  and a schema, a mechanical surface diff beats both heuristics on the only measure this history supports.
- **Limits of the oracle:** it sees names, not behaviour. A changed output format, a changed default or a narrower accepted input is
  not in it; this history has such changes (for example the pack layout) and the oracle calls them internal.

## Decision
Do not build `PublicAPI`, `DBSchema` and `RunbookDoc` graph schema for release auditing on this evidence: there is nothing to
recall, and the cheap mechanical diff already separates the additive releases from the rest. If a release audit is built, test it
for false alarms against this oracle (it must call 0 of the 13 internal releases breaking) and give it a history with real breaking
changes first (another repository's tags, or a seeded removal) before measuring recall.
