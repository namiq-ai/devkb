---
id: 5
type: story
title: "A C macro, constant or key that is not a Symbol is pointed to uses"
parent: epic-language-readiness
covers: [R10]
after: ["1.2", "1.5", "1.8"]
hitl: false
risk: low
---

# A C macro, constant or key that is not a Symbol is pointed to uses

## Description

In C (and C++) macros and constants are not graph nodes, and there is no qualified-name separator in C. Macros and constants are 3.3% of grep cost, modules and keys 7.9%. A `symbol` miss for `JSON_MAX_DEPTH` must lead to its `#define`, and two `static` functions of one name in two files must stay two answers.

## Requirements

1. **A macro or constant miss points to its definition** (R10)
   **Given** FX-C `JSON_MAX_DEPTH` (macro) and `MAX_NODES` (constant)
   **When** `symbol JSON_MAX_DEPTH` and `symbol MAX_NODES` run
   **Then** each says `no symbol named` and `C macros, constants and enum values are not graph symbols`, then shows the `uses` hits with the `#define` or declaration line first

2. **Static duplicates are separate answers ranked by file** (R10)
   **Given** FX-C where `static skip_ws` is in `src/json.c` and in `test/test_json.c`
   **When** `symbol skip_ws` runs
   **Then** two records are returned, `src/json.c` before the test, each with its own range

3. **C has no qualified name, and the reply does not pretend** (R10)
   **Given** FX-C
   **When** `symbol "json.json_parse"` runs
   **Then** the reply is `no symbol named` with `C has no qualified names; use path::name`, and `symbol "src/json.c::json_parse"` finds it

4. **The note is C-only** (R10)
   **Given** FX-PY
   **When** an unknown constant is searched
   **Then** the reply has no C note

## Boundaries

- Must not change: C ranges (99.8% exact); the `language` property is not read (backlog 5).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-language-readiness/epic-language-readiness.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 8
- analysis — docs/analysis/read-tools-analysis.md, section 1 (constant or macro 3.3%)
