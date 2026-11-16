---
id: 1
type: story
title: "Every File and Symbol says whether it is C or C++"
parent: epic-language-profiles
covers: [R1]
after: []
hitl: false
risk: low
---

# Every File and Symbol says whether it is C or C++

## Description

Tracer for D7. The scanner already knows each file's path and whether a `.h` looks like C++; this story writes the answer into the graph as `language` on File and Symbol and adds `linkage` to Symbol, so every later story reads one property instead of re-deciding.

## Requirements

1. **A C, a C++ and a plain header file each carry their language** (R1)
   **Given** tests/fixtures/profiles/basic holds `a.c`, `b.cpp` and `c.h` (plain C declarations, no includer)
   **When** `devkb build --project tests/fixtures/profiles/basic` runs
   **Then** the File nodes have `language` `c`, `cpp` and `c`, and each Symbol's `language` equals the language of its File
   **And** `linkage` is `internal` for a `static` function, `c` for a non-static C function, `cpp` for a C++ function outside `extern "C"`

2. **No C or C++ node is left without `language`** (R1)
   **Given** the same build
   **When** `pytest tests/test_language_profiles.py::test_language_on_every_node` runs
   **Then** it finds zero File or Symbol nodes of C/C++ source without `language`, and it fails when the extractor's output for one file drops the property (seeded in the test)

3. **A repository with no C or C++ file is unchanged** (R1)
   **Given** this repository and a Python fixture
   **When** `nodes.jsonl` and `edges.jsonl` are built before and after the change
   **Then** `diff` shows no difference (Python and TypeScript nodes get no `language`)

4. **The ontology names the new properties and nothing else** (R1)
   **Given** the change
   **When** `git diff -- devkb/ontology.md` is read
   **Then** it adds only the `language` and `linkage` rows to the File and Symbol property tables, and `ADR-DEVKB-009` is Accepted

## Boundaries

- Must not change: C++ call resolution, packs and edges; Python and TypeScript nodes.
- Not here: deciding a `.h` file's language beyond today's rule (story 2).

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-language-profiles/epic-language-profiles.md
- spec — docs/spec/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
