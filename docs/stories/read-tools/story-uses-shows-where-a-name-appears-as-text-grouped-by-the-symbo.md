---
id: 8
type: story
title: "uses shows where a name appears as text, grouped by the symbol that holds it"
parent: epic-core-read-tools
covers: [R7]
after: [2]
hitl: false
risk: medium
---

# uses shows where a name appears as text, grouped by the symbol that holds it

## Description

D5. `uses(name)` and `devkb uses NAME` (ADR-DEVKB-010 section 5) are a text search annotated with the graph. They cover modules, constants, macros and keys that are not graph nodes (11% of grep cost) without a schema change, and they say every time that they are text matches, not resolved references, and not complete.

## Requirements

1. **The reply is labelled and never claims completeness** (R7)
   **Given** any fixture
   **When** `uses X` runs
   **Then** the first line is `uses "X": text matches, not resolved references; tracked files only, not complete` and no reply of this tool contains the word `Complete`

2. **A name with no node is found** (R7)
   **Given** FX-C where `JSON_MAX_DEPTH` is a `#define` and `MAX_NODES` a constant, and FX-MIX `app.cfg` holding the key `retry_limit`
   **When** `uses JSON_MAX_DEPTH` and `uses retry_limit` run
   **Then** each lists its lines as `path:line  top level  <line>` or inside a function as `in <qualified name>`, with `mode word`

3. **Hits are grouped by file and by enclosing symbol, production first** (R7)
   **Given** FX-PY where `load_config` is called in `app/util.py` and in `tests/test_config.py`
   **When** `uses load_config` runs
   **Then** `defined: app/config.py L40-71 function` comes first, then the `app/` hits, each `in <enclosing symbol>` taken from the Symbol ranges, then the test file

4. **A start-only file says after, not in** (R7)
   **Given** FX-TS where `parseKey` is used inside a function whose stored range has no end
   **When** `uses parseKey` runs
   **Then** the hit says `after <symbol>`, never `in`

5. **The mode follows the query** (R7)
   **Given** FX-PY
   **When** `uses load_config`, `uses "load_.*g"` and `uses "app/config"` run
   **Then** the modes printed are `word`, `regex` and `text`; a word search does not match `load_config_text`; an invalid expression says `bad regular expression: <reason>` and nothing else

6. **Caps are enforced and reported** (R7)
   **Given** a fixture text with 40 hits of one word across 15 files
   **When** `uses` runs on it
   **Then** at most 12 files, 36 hits and 3 hits per file are shown and the last line reads `showing <h> of 40 hits in <f> of 15 files; omitted: <n> hits (<t> in tests), <m> files. Narrow with under=PATH.`

7. **Skipped files are counted** (R7)
   **Given** a repository with a lockfile, a `dist/` file, a binary and a 2 MB text file
   **When** `uses` runs
   **Then** none is searched and the reply says `skipped: 4 files (generated, binary, over 1 MB)`

8. **The result is fast and the graph is unchanged** (R7)
   **Given** a synthetic repository of 5,000 small files
   **When** `uses` runs once
   **Then** it returns in under 1 s on the CI runner, and `nodes.jsonl` and `edges.jsonl` of every fixture are unchanged

## Boundaries

- Must not change: `callers`, `pack`, `tests_for`.
- Not here: untracked files; resolved references.

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 2, 5
- analysis — docs/analysis/read-tools-analysis.md, section 1

## Notes

- Assumption: the search covers `git ls-files`; a repository that is not a git checkout is walked.
