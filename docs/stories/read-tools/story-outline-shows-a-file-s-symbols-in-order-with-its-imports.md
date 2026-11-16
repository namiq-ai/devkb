---
id: 6
type: story
title: "outline shows a file's symbols in order, with its imports"
parent: epic-core-read-tools
covers: [R6, R9]
after: [2]
hitl: false
risk: medium
---

# outline shows a file's symbols in order, with its imports

## Description

An outline of a file is 11.9% of grep cost. This story builds `outline(path)` and `devkb outline PATH` of ADR-DEVKB-010 section 4 for a file, a directory and a path suffix, and registers the tool in `lean-pack`, `dev` and `all`.

## Requirements

1. **A file lists its symbols in source order with nesting** (R6)
   **Given** FX-PY `app/config.py` holding `Config` (methods `get`, `reload`) and `load_config`
   **When** `devkb outline app/config.py --project tests/fixtures/readtools/py` runs
   **Then** the header reads `app/config.py  Python <n> symbols  range=exact`, then `class Config`, its two methods indented below it, then `load_config`, each with `L<start>-<end>` from `expected.json` and the first docstring line

2. **The imports come from the file's text** (R6)
   **Given** the same file importing `yaml` and `os`
   **When** the outline runs
   **Then** the import lines appear before the first symbol, at most 30; the C fixture shows its `#include` lines and the C# fixture its `using` lines

3. **A start-only file prints starts only** (R6, R9)
   **Given** FX-TS `src/config.ts`
   **When** `outline src/config.ts` runs
   **Then** every symbol shows `L<start>` with no end, the header says `range=start-only`, and no nested line claims a parent the qualified name does not give

4. **A unique suffix resolves, an ambiguous one lists candidates** (R6)
   **Given** FX-PY with `app/config.py` and `tests/test_config.py`
   **When** `outline config.py` and `outline test_config.py` run
   **Then** the second resolves to the test file; the first lists both paths (at most 8) and asks for a longer one; a path matching nothing says `no file named`; `outline ../x` says `path outside the repository`

5. **A directory lists its files with symbol counts** (R6)
   **Given** FX-PY
   **When** `outline app` runs
   **Then** each tracked file under `app/` is a line `path  <n> symbols`, files with no symbols last, subdirectories collapsed as `dir/  <n> files  <n> symbols`, at most 60 lines with `(N more files)`

6. **A file with no indexed symbols says so** (R6)
   **Given** FX-MIX `app.cfg` and `Makefile`
   **When** `outline app.cfg` runs
   **Then** the reply is `no indexed symbols in app.cfg`, then `indexed languages: Python, TypeScript, JavaScript, C#, C, C++, Odoo XML`, then the line count; it does not say the file is empty

7. **The tool is registered and the graph is unchanged** (R1)
   **Given** the MCP server with `--toolset lean-pack`, `dev` and `all`
   **When** the tool list is read and `nodes.jsonl` is compared before and after
   **Then** `outline` is in each toolset and there is no graph difference

## Boundaries

- Must not change: Symbol ranges and names as stored.
- Not here: source bodies (1.7); per-language gap replies (epic 2).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 2, 4, 8
