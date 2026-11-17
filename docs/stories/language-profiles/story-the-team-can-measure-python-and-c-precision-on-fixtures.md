---
id: 7
type: story
title: "The team can measure Python-and-C precision on fixtures"
parent: epic-cross-language-boundaries
covers: [R17]
after: [5, 6]
hitl: false
risk: medium
---

# The team can measure Python-and-C precision on fixtures

## Description

The closing measure for Python and C: a labelled truth for every boundary fixture, with negatives, and a check that reports precision and recall per mechanism. Owner decision: fixtures and their own measure first; no real corpus yet.

## Requirements

1. **Every boundary fixture is labelled** (R17)
   **Given** tests/fixtures/boundaries/truth.json
   **When** it is read
   **Then** it lists, per fixture, each true edge `{caller, callee, mechanism}` and each negative case (dynamic, ambiguous, not a library handle, not in the repository)

2. **Precision is 1.0 and every dynamic case is unresolved** (R17)
   **Given** the labelled fixtures
   **When** `python3 bench/boundaries/check.py tests/fixtures/boundaries` runs
   **Then** it prints precision and recall per mechanism (`extern-c`, `ctypes`, `cffi`, `pyc-api`, `pybind11`), precision is 1.0, every negative produces no edge, and every dynamic case is counted unresolved; exit 0

3. **A wrong link exits 1** (R17)
   **Given** a test that makes the resolver ignore uniqueness for its own run
   **When** the check runs
   **Then** it exits 1 and names the false edge

4. **The check shares no code with the extractors** (R17)
   **Given** `bench/boundaries/check.py`
   **When** a test scans its imports
   **Then** it imports only `json` and the standard library, and reads edges from `edges.jsonl`

5. **The exported-symbol note is measured for noise** (R12)
   **Given** the pinned Zephyr clone
   **When** `make cpp-check` runs
   **Then** it prints the share of C packs that carry the note, so the owner can decide the open question on noise

## Boundaries

- Must not change: `make gate-1` and `make gate-2`; the fixtures run in gate-2, the real-corpus line does not.
- Out: a real-world Python and C corpus (open question).

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
