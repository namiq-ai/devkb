---
id: 1
type: story
title: "symbol answers an exact name with file, range, signature, callers and the staleness note"
parent: epic-core-read-tools
covers: [R1, R2, R4]
after: []
hitl: false
risk: medium
---

# symbol answers an exact name with file, range, signature, callers and the staleness note

## Description

Tracer for D1 and D2. It puts the exact tier of `symbol` through every layer on the Python fixture FX-PY (a minimal `tests/fixtures/readtools/py/`, created here; the other five fixtures are story 1.2): the index lookup, the text reply of ADR-DEVKB-010 section 3.3, the MCP tool in `lean-pack`, `dev` and `all`, the `devkb symbol` command, and the staleness note. It replaces the old `symbol(name, limit)` JSON method; its two existing tests are updated, not deleted.

## Requirements

1. **An exact name returns one record per match** (R2, R4)
   **Given** FX-PY built with `devkb build --project tests/fixtures/readtools/py`, holding `load_config` defined once, with a docstring and 3 direct callers
   **When** `devkb symbol LOAD_CONFIG --project tests/fixtures/readtools/py` runs (upper case on purpose)
   **Then** the first line reads `symbol "LOAD_CONFIG": 1 match (exact)`, and the record shows the file, kind, `L<start>-<end>` equal to the line numbers in FX-PY's `expected.json`, the signature line as it is in the file, the docstring's first line, `callers 3` and `how exact`
   **And** the reply is plain text with no JSON braces

2. **A name that does not exist gets one honest line** (R2)
   **Given** the same build
   **When** `devkb symbol zzz_not_here` runs
   **Then** the reply says `no symbol named "zzz_not_here"` and no match record; the exit status is 0

3. **A stale graph ends the reply with the staleness note** (R1)
   **Given** the FX-PY repository has a commit made after the build (the test commits a change in a temporary copy)
   **When** `symbol` is called through the MCP tool
   **Then** the last line starts `graph stale: built at` and gives the build head and the number of commits ahead; with a fresh graph there is no such line

4. **The tool is in the three toolsets and is the same on both doors** (R1)
   **Given** the MCP server built with `--toolset lean-pack`, `dev` and `all`
   **When** the tool list is read
   **Then** `symbol` is in each of the three; the MCP reply and the shell reply for the same query are byte-identical apart from the command's own trailing newline

5. **The old JSON method is gone and its tests follow** (R1)
   **Given** `tests/test_devkb_mcp_odsf307.py` and `tests/test_devkb_process_api_odsf309.py`, which read the old reply
   **When** the full suite runs
   **Then** it passes, and `git grep -n '"symbols": \[' devkb/process_api.py` finds no reply built for `symbol`

6. **The graph files do not change** (R1)
   **Given** `nodes.jsonl` and `edges.jsonl` of FX-PY built before and after the change
   **When** they are compared with `diff`
   **Then** there is no difference

## Boundaries

- Must not change: the other tools' JSON replies and `_meta`; `find_code`.
- Not here: tiers 2 to 7 (1.3, 1.4), ranking and filters (1.5), source (1.7), the other five fixtures (1.2).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 2, 3.1 tier 1, 3.3, 7, 9 (FX-PY)

## Notes

- Assumption: caller count is direct CALLS callers, one hop.
