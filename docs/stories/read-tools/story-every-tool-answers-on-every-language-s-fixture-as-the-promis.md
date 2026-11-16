---
id: 11
type: story
title: "Every tool answers on every language's fixture as the promise table says"
parent: epic-core-read-tools
covers: [R9]
after: [10]
hitl: false
risk: medium
---

# Every tool answers on every language's fixture as the promise table says

## Description

The closing end-to-end suite of the epic: the four tools on the six fixtures, every cell checked against ADR-DEVKB-010 section 8. It is the test that fails when a reply promises more than a language's graph holds. Epic 2 adds the per-gap stories beside it.

## Requirements

1. **The matrix is complete** (R9)
   **Given** the six fixtures and the four tools
   **When** `pytest tests/test_readtools_matrix.py -v` runs
   **Then** it reports 24 cells (tool by fixture), each with at least one assertion from `expected.json`, and a cell with no assertion fails

2. **No reply states an end line it does not hold** (R9)
   **Given** FX-TS and the Odoo XML symbols of FX-MIX (start-only)
   **When** `symbol` with and without `source=True` and `outline` run on every symbol
   **Then** no reply contains an `L<start>-<end>` range for them, and every range printed for the other languages equals `expected.json`

3. **Every exact range is exact** (R9)
   **Given** FX-PY, FX-CS, FX-C and FX-CPP
   **When** `symbol NAME source=True` runs for every expected symbol
   **Then** the last returned line number equals the expected end line

4. **A miss never contradicts the graph** (R9)
   **Given** every `not_indexed` entry of every `expected.json`
   **When** `symbol` runs on it
   **Then** the reply is not a bare "no symbol named": it carries the language's note (exact wording in epic 2) or at least the `uses` hint

5. **Both doors agree** (R1)
   **Given** each of the 24 cells
   **When** the MCP tool and the shell command are called with the same arguments
   **Then** the replies are byte-identical

6. **The graph is unchanged and the speed holds** (R1)
   **Given** the six fixtures
   **When** their `nodes.jsonl` and `edges.jsonl` are compared with the pre-change build, and `uses` and `search_docs` are timed on a 5,000-file synthetic tree
   **Then** there is no difference and each returns in under 1 s

## Boundaries

- Must not change: the replies themselves; a failing cell is fixed in its tool's story.
- Not here: the per-gap wording (epic 2); the benchmark (1.12).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 8, 9
