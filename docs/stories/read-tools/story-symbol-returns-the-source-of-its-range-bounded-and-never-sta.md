---
id: 7
type: story
title: "symbol returns the source of its range, bounded, and never states an end it does not have"
parent: epic-core-read-tools
covers: [R5, R9]
after: [5, 6]
hitl: false
risk: high
---

# symbol returns the source of its range, bounded, and never states an end it does not have

## Description

D3, the riskiest rule of the epic: a wrong end line makes an agent read the wrong code and trust it. `source=True` and `lines` of ADR-DEVKB-010 section 3.5 return the lines of the range, bounded by the graph's own `line_start` and `line_end` where the capability table says `range=exact`, and say `end unknown` where it says `start-only`. A grep `-A25` over-reads 87% of Python functions and cuts 11% short; bodies are under 80 lines for 97 to 99% of Python and C#.

## Requirements

1. **An exact range returns exactly its lines** (R5)
   **Given** FX-PY `load_config` at `L40-71` in `expected.json`
   **When** `symbol load_config source=True` runs
   **Then** the reply holds the lines 40 to 71 of the file, each prefixed with its line number, and nothing before 40 or after 71

2. **A long body is cut at the cap and says so** (R5)
   **Given** a function of 150 lines in FX-C `src/json.c`
   **When** `symbol json_parse source=True` runs, and again with `lines=300`
   **Then** the first reply shows 80 lines then `(70 more lines; L<s>-<e>)`; the second shows 200 lines, says `lines capped at 200` and `(N more lines; ...)` with the exact remainder

3. **A start-only symbol says end unknown and shows a window** (R5, R9)
   **Given** FX-TS `loadConfig` whose stored `line_end` equals `line_start`
   **When** `symbol loadConfig source=True` runs
   **Then** the record shows `L<start> (end unknown)`, the source block holds at most 40 lines from the start and is headed `approximate window, not the symbol's range`, and the reply contains no end line number anywhere

4. **A class that does not fit returns its outline instead** (R5)
   **Given** FX-PY `Config` with 6 methods spanning more than `lines=10`
   **When** `symbol Config source=True lines=10` runs
   **Then** the reply is the outline of `Config` (its nested symbols as `outline` prints them), headed `class range L<s>-<e> exceeds 10 lines: outline shown`; with `lines=80` the same call returns the body

5. **A moved symbol says moved and returns no source** (R5)
   **Given** a copy of FX-PY in which three lines were inserted above `load_config` after the graph was built
   **When** `symbol load_config source=True` runs on the stale graph
   **Then** the record says `moved: "load_config" is not at L40; the file changed after the graph was built`, no source block is returned, the reply names `uses load_config`, and the staleness note ends the reply

6. **Source is read inside the repository only** (R5)
   **Given** a Symbol key whose path would resolve outside the repository root (a crafted graph in the test)
   **When** `symbol` runs with `source=True`
   **Then** the reply says `path outside the repository` and reads no file

7. **Only the first match carries source** (R5)
   **Given** FX-PY `get` with two matches
   **When** `symbol get source=True` runs
   **Then** the first match has a source block and the second a line `source: call again with path::name`

## Boundaries

- Must not change: the match record fields of 1.1 and the order of 1.5.
- Not here: the extractor end line of TypeScript (backlog 3); this story only reads what is stored and says what is not.

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 1, 3.5
- analysis — docs/analysis/read-tools-analysis.md, sections 2 and 3

## Notes

- Check beyond the criteria: run `symbol ... source=True` over every Symbol of FX-PY, FX-C and FX-CS and compare the returned last line with `expected.json`; any difference is a failure, not a footnote.
- Assumption: a `moved` symbol returns no source.
