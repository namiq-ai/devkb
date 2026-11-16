---
id: 3
type: story
title: "TypeScript and JavaScript symbols store their real end line"
parent: none
covers: []
after: []
assignee: ""
refined: false
hitl: false
risk: medium
---

# TypeScript and JavaScript symbols store their real end line

## Description

**Prerequisite** of the TypeScript half of the read tools (SPEC-DKB-003, D7): with it, `symbol(..., source=True)` can return a TypeScript or JavaScript body bounded by the graph's own range and the 95% end-line floor can be claimed. It is not a prerequisite of the tools shipping: until it lands they say `end unknown` and show a 40-line approximate window (story 2.1 of the read-tools initiative). Filed 2026-11-16 by the owner's request; it can be built on its own, first.

**Who is blocked and why.** An agent asking for a TypeScript function's source cannot be given its range, so it falls back to `grep -A` or reads the whole file. In mealie 632 of 632 TypeScript Symbols have `line_end == line_start`, and end line is exact for 12.9% of them (the shared one-liners).

**Evidence** (from `docs/analysis/read-tools-analysis.md`, section 2):

```
python3 bench/readtools/range_accuracy.py <mealie checkout> <mealie graph dir> typescript
```

reports 631 symbols, recall 0.58, precision 1.00, end line exact **12.9%**. The cause is one line: `build_symbols.py` (around line 1248) writes `line_end=s["line_start"]` for each symbol of `ts_symbols.extract_file`, although `ts_symbols._find_symbols` already returns `body_end` for each symbol. JavaScript is read by the same extractor.

**Terminal state.** For every TypeScript and JavaScript Symbol whose body the extractor delimits, `line_end` is the line of the body's last character; a symbol whose body it cannot delimit keeps `line_end == line_start`. The end-line exact share on mealie is at least 95%.

**Scope boundary.** In: `ts_symbols.extract_file` returning the end line, `build_symbols.py` writing it, the capability table row for `.ts .tsx .js .jsx .mjs .cjs` flipping from `start-only` to `exact`, and the read-tool tests that assert `end unknown` for TypeScript. Out: Odoo XML ranges (same `line_end = line_start`, a separate extractor); class-method and nested-declaration recall (0.58, see note); any new node type, edge or property.

**Where to start.** `devkb/ts_symbols.py` `_find_symbols` and `extract_file` (the offsets to line numbers conversion), then `devkb/build_symbols.py` where TypeScript symbols are added to the graph.

**Owner rationale.** The graph's own range is what lets the tool avoid a second parse; the extractor already did the work and the build throws it away. A small change with the largest effect on one language's tools.

## Acceptance Criteria

1. **The extractor returns the end line**
   **Given** a TypeScript file with a function of 12 lines, an arrow function assigned to a `const` over 3 lines, a class of 40 lines and a one-line function
   **When** `ts_symbols.extract_file` runs on it (`pytest tests/test_ts_symbols_end_line.py`)
   **Then** each symbol has `line_end` equal to the last line of its body (12-line function: start+11), and the one-line function has `line_end == line_start`

2. **The graph stores it**
   **Given** the FX-TS fixture of the read-tools initiative, or a fixture of the same shape if that is not built
   **When** `devkb build` runs and `nodes.jsonl` is read
   **Then** every TypeScript and JavaScript Symbol has `line_end >= line_start`, and the functions above have the ends of criterion 1

3. **The floor holds on a real repository**
   **Given** the mealie checkout and its rebuilt graph
   **When** the command in Evidence runs
   **Then** end line exact is at least 95% and precision stays 1.00

4. **Nothing else in the graph changes**
   **Given** the same repository built before and after
   **When** the two `nodes.jsonl` and `edges.jsonl` are compared
   **Then** the only differences are `line_end` on TypeScript and JavaScript Symbols; Python, C# and C/C++ nodes, and all edges, are identical, and the build time changes by less than 5%

5. **The read tools stop saying end unknown for TypeScript**
   **Given** the capability row for `.ts` set to `exact`
   **When** `pytest tests/test_readtools_lang_ts.py tests/test_readtools_source.py tests/test_readtools_matrix.py` runs
   **Then** the assertions that expected `end unknown` for TypeScript are updated and pass, and the 95% floor of story 2.6 is asserted

## References

- spec — docs/spec/SPEC-DKB-003_read-tools-for-every-language.md, Gaps GAP-5
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 1 and 8
- analysis — docs/analysis/read-tools-analysis.md, section 2 findings 2 and 3
- initiative — _bmad-output/initiative-read-tools-for-every-language/ (story 2.1, story 2.6)

## Notes

- Note (not a ticket): TypeScript recall is 0.58 because class methods and nested declarations are not found; precision is 1.00. It is a separate piece of work, to be filed when the owner asks. The read tools say so on a miss.
- Assumption: Odoo XML is out; the owner can file it beside this.
- Open question: whether `body_end` is exact for arrow functions with expression bodies (`_expr_body_end`); criterion 1 checks one, the mealie measure checks the rest.
