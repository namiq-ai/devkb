---
id: 7
type: story
title: "A name defined in two languages shows each match under its own language's promise"
parent: epic-language-readiness
covers: [R9]
after: ["1.2", "1.5", "1.7"]
hitl: false
risk: low
---

# A name defined in two languages shows each match under its own language's promise

## Description

In a mixed repository (Python wrapping a C library, a TypeScript front end) one name can be defined in several languages with different promises: exact range here, start-only there. There is no `language` property on main (backlog 5), so each match takes its promise from its own file's extension through the capability table.

## Requirements

1. **Each match uses its own file's capability** (R9)
   **Given** FX-MIX with `add_one` in `bind/lib.c` (exact) and in `bind/wrap.py` (exact) and a start-only `add_one` in `ui/app.ts`
   **When** `symbol add_one` runs
   **Then** all three are `how exact`; the C and Python matches show `L<s>-<e>`, the TypeScript match shows `L<s> (end unknown)`, and no match takes another file's capability

2. **A source reply is for one match and says which** (R9)
   **Given** the same
   **When** `symbol add_one source=True` runs
   **Then** the source block belongs to the first match by the ranking rule and is headed with its path; the other matches say `source: call again with path::name`

3. **The table is the only place an extension is read** (R9)
   **Given** the new tests
   **When** the grep of story 1.2 criterion 4 runs again
   **Then** it still finds extension strings only in the capability table module, so backlog 5 can replace its input

## Boundaries

- Must not change: ranking (1.5).
- Not here: cross-language edges (SPEC-DKB-002).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-language-readiness/epic-language-readiness.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 1
- backlog — _bmad-output/backlog/story-every-symbol-carries-its-language-and-a-range-capability.md
