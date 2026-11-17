---
id: 3
type: story
title: "The team can prove extern-c edges against the compiler on autoas"
parent: epic-cross-language-boundaries
covers: [R13, R17]
after: [2]
hitl: true
risk: medium
---

# The team can prove extern-c edges against the compiler on autoas

## Description

Proves `extern-c` against the compiler. `bench/cpp/quality.py` scores edges against `truth_clang.py` but not by edge `source`; this story adds that split and the autoas edge counts. A person approves the floor.

## Requirements

1. **`extern-c` precision is scored against the compiler truth** (R17)
   **Given** autoas at its pinned commit (`cc37096`, resolved to 40 characters) and `python3 bench/cpp/truth_clang.py AUTOAS_DIR truth_autoas.json --std c++17`
   **When** `python3 bench/cpp/quality.py WORKTREE AUTOAS_DIR truth_autoas.json` runs
   **Then** the JSON has `by_source.extern-c` with `edges`, `precision`, `recall`, `unmapped`; precision is at or above the committed floor (initial 0.95); exit 0

2. **The existing cross-language edges keep linking** (R13)
   **Given** the same run
   **When** `extern-c` edges are counted by caller language and callee language
   **Then** C++-to-C is at least 279 and C-to-C++ at least 61, or each lost edge is listed in the story's notes with the rule that now refuses it (precision-driven loss)

3. **Compiler truth is independent of devkb** (R17)
   **Given** `bench/cpp/truth_clang.py`
   **When** a test scans its imports
   **Then** it imports nothing from `devkb`

4. **A seeded fault is caught** (R17)
   **Given** a test that disables the uniqueness rule of the resolver for its own run on tests/fixtures/boundaries/extern_c
   **When** `quality.py` scores it
   **Then** `extern-c` precision falls below the floor and the check exits 1

5. **The build stays inside its budget** (R13)
   **Given** `make cpp-check`
   **When** the budget lines print
   **Then** Zephyr builds in under 120 s and cJSON in under 5 s on the recorded reference machine

## Boundaries

- Must not change: `make gate-1`, `make gate-2` (offline); `docs/BENCHMARK.md`.
- Out: Python and C measures (story 7).

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
