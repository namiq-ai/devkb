---
id: 1
type: story
title: "A TypeScript, JavaScript or Odoo XML symbol is shown from its start, and missing class methods are named"
parent: epic-language-readiness
covers: [R10]
after: ["1.2", "1.3", "1.7"]
hitl: false
risk: medium
---

# A TypeScript, JavaScript or Odoo XML symbol is shown from its start, and missing class methods are named

## Description

Tracer of epic 2 and the weakest data: TypeScript, JavaScript and Odoo XML store `line_end = line_start` for every symbol (632 of 632 in mealie), and TypeScript finds only 58% of definitions (class methods and nested declarations are missing). Until backlog 3 stores the real end, the tools must say `end unknown`; a miss on a method must not read as proof. This story proves that on FX-TS and the Odoo XML of FX-MIX.

## Requirements

1. **A start-only symbol is shown from its start** (R10)
   **Given** FX-TS `loadConfig`
   **When** `symbol loadConfig` and `outline src/config.ts` run
   **Then** both print `L<start> (end unknown)` or `L<start>`, never a range, and `symbol ... source=True` returns a window headed approximate (the 1.7 rule, here checked on this language)

2. **A miss on a missing class method names the gap** (R10)
   **Given** FX-TS `class Store` whose `get` the graph does not hold (listed in `expected.json` under `not_indexed`)
   **When** `symbol Store.get` and `symbol get` run
   **Then** the reply says `no symbol named "Store.get"` and `TypeScript and JavaScript class methods and nested declarations are often not indexed (about 4 in 10 definitions)`, and runs the `uses` search for the name, showing its first 3 hits

3. **An object-literal entry resolves by container.entry** (R10)
   **Given** FX-TS `src/routes.js` with `routes.list` and `routes.show`
   **When** `symbol routes.list` runs
   **Then** `routes.list` is returned `how qualified`, with `L<start> (end unknown)`

4. **Odoo XML declarations are start-only too** (R10)
   **Given** an Odoo view declaration in FX-MIX's `ui/` folder
   **When** `symbol` finds it
   **Then** the record shows `L<start> (end unknown)` and the reply carries the same approximate-window rule

5. **The note leaves with the data** (R10)
   **Given** the capability table row for `.ts`
   **When** the row is changed to `range=exact` (what backlog 3 does)
   **Then** the test for this story fails only on the `end unknown` assertions and the note's `not indexed` assertion remains, so the person fixing backlog 3 sees which assertions to update

## Boundaries

- Must not change: Python, C#, C and C++ replies.
- Not here: storing the end line (backlog 3); class-method recall (a note in backlog 3).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-language-readiness/epic-language-readiness.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 3.5, 8
- backlog — _bmad-output/backlog/story-typescript-and-javascript-symbols-store-their-real-end-line.md
