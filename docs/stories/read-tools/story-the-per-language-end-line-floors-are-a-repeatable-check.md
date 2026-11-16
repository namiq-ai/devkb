---
id: 6
type: story
title: "The per-language end-line floors are a repeatable check"
parent: epic-language-readiness
covers: [R12]
after: ["1.2"]
hitl: true
risk: medium
---

# The per-language end-line floors are a repeatable check

## Description

D7's accuracy floors: end line exact at least 99% for Python and C#, 92% for C and C++, 95% for TypeScript after backlog 3. `bench/readtools/range_accuracy.py REPO GRAPH LANG` measures it once; this story makes it one documented command that fails below a floor, so a change to an extractor cannot silently break `source=True`. A person sets up the corpora (clones at pinned commits, the tree-sitter packages and libclang truth), which is why it is hitl.

## Requirements

1. **One command runs every language** (R12)
   **Given** the pinned corpora (click, httpx, MediatR, FluentValidation, cJSON, leveldb, fmt, mealie) cloned by a documented script
   **When** `make readtools-floors` (or the command the story documents) runs
   **Then** it builds each graph, runs `range_accuracy.py` per language and prints a table language, repository, symbols, end-line exact share, floor, verdict

2. **A floor below its number fails the run** (R12)
   **Given** the table
   **When** a language's exact share is under its floor (Python and C# 99%, C and C++ 92%)
   **Then** the command exits non-zero and names the repository; a seeded run with one extractor made to shift every end line by one fails

3. **TypeScript's floor is conditional and says so** (R12)
   **Given** backlog 3 not done
   **When** the command runs
   **Then** TypeScript is printed as `floor 95%: not claimed, range=start-only (backlog 3)` and does not fail the run; once the capability table row for `.ts` says `exact`, the 95% floor is asserted

4. **The result is committed with its inputs** (R12)
   **Given** a run
   **When** its output is saved to `docs/analysis/read-tools-floors.md`
   **Then** it states each corpus commit, the tool versions and the date

## Boundaries

- Must not change: `range_accuracy.py`'s measure (the numbers of the analysis must reproduce).
- Not here: raising an extractor's accuracy.

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-language-readiness/epic-language-readiness.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 8 (floors)
- analysis — docs/analysis/read-tools-analysis.md, section 2

## Notes

- hitl: a person clones the corpora and installs `tree-sitter` and the libclang truth (not dependencies of devkb).
- Open question: a real C# corpus with generics-heavy code for the 99% floor.
