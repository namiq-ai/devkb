---
id: 5
type: story
title: "Every symbol carries its language and a range capability"
parent: none
covers: []
after: []
assignee: ""
refined: false
hitl: false
risk: medium
---

# Every symbol carries its language and a range capability

## Description

**Not for now.** Filed 2026-11-16 by the owner's request; nothing here is built until the owner starts it. The read tools work without it: they read capability from the file's extension through one table (ADR-DEVKB-010 section 1), and this ticket replaces that table's input.

**Who is blocked and why.** The tools infer capability from the extension, which cannot tell a `.h` file's C from its C++, cannot know that a generated or renamed file belongs to another language, and has to be edited in the tools when a language is added. `language` is not on main: it exists only for C and C++ on the unmerged SPEC-DKB-002 branch (story 1.1 of the language-profiles initiative).

**Evidence.**

```
grep '"type": "Symbol"' <graph dir>/nodes.jsonl | grep -c '"language"'
```

prints `0` on main for a Python, TypeScript or C# repository (the property exists only on the unmerged SPEC-DKB-002 branch, for C and C++). After this ticket it prints the number of Symbols, and the same command with `"range"` does too.

**Terminal state.** Every Symbol and File carries `language` (`python`, `typescript`, `javascript`, `csharp`, `c`, `cpp`, `odoo-xml`) and every Symbol carries the capability flag `range` = `exact` or `start-only`; the read tools read these first and use the extension table only for a node that lacks them.

**Scope boundary.** In: the properties on File and Symbol written by each extractor, `devkb/ontology.md` (through an Accepted ADR, `ADR-SDP-DEVKB-001`), `KEEP_PROPS`, the capability function. Out: any reply change; the `linkage` and boundary properties of SPEC-DKB-002; the extractors' accuracy.

**Where to start.** SPEC-DKB-002 story 1.1 (the `language` property for C and C++): land or reconcile it first, so there is one `language` property with one value set, then extend it to the other extractors in `build_symbols.py`, `csharp_symbols.py`, `cpp_graph.py`.

**Owner rationale.** The tools should not infer a fact the extractor knows; one property makes a new language a row in an extractor, not a branch in four tools.

## Acceptance Criteria

1. **Every node has a language and a range flag**
   **Given** each of the six read-tools fixtures built
   **When** the Evidence command and a variant for `range` run
   **Then** no Symbol or File lacks `language` and no Symbol lacks `range`; `range` is `start-only` exactly for TypeScript and JavaScript until backlog 3 and for Odoo XML, `exact` otherwise

2. **The two ADRs agree**
   **Given** `docs/adr/ADR-DEVKB-009` (D7, `language` for C and C++) and a new ADR for this ticket
   **When** they are read
   **Then** one value set for `language` is defined once, the new ADR is Accepted before the first change merges, and `devkb/ontology.md` lists the two properties

3. **The tools read the property first**
   **Given** the capability function
   **When** `pytest tests/test_readtools_capability.py` runs with a node whose `range` disagrees with its extension row
   **Then** the node's property wins; a node without the property falls back to the extension row

4. **No reply changes**
   **Given** the six fixtures
   **When** `pytest tests/test_readtools_matrix.py` runs
   **Then** it passes without edits to its expected replies

5. **The graph differs only by the new properties**
   **Given** a repository built before and after
   **When** `nodes.jsonl` and `edges.jsonl` are compared
   **Then** the only differences are the added `language` and `range` properties (and `language` of C and C++ equal to those of SPEC-DKB-002 story 1.1); edges are identical

## References

- spec — docs/spec/SPEC-DKB-003_read-tools-for-every-language.md, Gaps GAP-7
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 1; docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md, section 2
- sibling — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-language-profiles/tickets/story-every-file-and-symbol-says-whether-it-is-c-or-c.md

## Notes

- Open question: the `range` flag may be derivable (`line_end > line_start`) but a one-line function is legitimately equal; the owner asked for an explicit flag, so it is stored.
- Open question: which lands first, SPEC-DKB-002 story 1.1 or this ticket; the criteria above hold either way if the value set is shared.
