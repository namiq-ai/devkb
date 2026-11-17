---
tracker_id: ""
id: 1
type: epic
title: "C and C++ are separate rule profiles that each report their own Complete"
parent: initiative-language-profiles-and-boundaries
covers: [R1, R2, R3, R4, R5, R6, R7]
sources: []
companions: []
after: []
refined: true
risk: medium
---

# C and C++ are separate rule profiles that each report their own Complete

## Description

Decision D7. One scanner keeps reading both languages, but a `language` property and a per-profile rule set stop C being judged by C++ rules. The headline evidence: Zephyr has 10,044 `.c`, 5,802 `.h` (2 with C++ constructs, 1,640 with an `extern "C"` guard) and 70 C++ files; autoas has 210 `.c`, 132 C++ files and 94 of 225 headers with the guard. Today `cpp_symbols.looks_cpp` reads a `.h` as C++ when it holds `class`, `namespace`, `template` or `::`, with no includer information and no marking of the guard.

## Outcome

An agent asking about a C function gets a C pack, judged by linkage and with C's own limits; an agent asking about a C++ method gets the C++ pack it gets today.

## Requirements

R1 (parent R1): `language` (`c` or `cpp`) is recorded on every File and Symbol; a build over the pinned corpus leaves none without it.
R2 (parent R2): a `.h` file's language is decided by what it contains and what includes it; an `extern "C"` guard marks a C header consumed by C++; the default is `c`.
R3 (parent R3): the C profile resolves through linkage; function-pointer tables and ops structs are unresolved indirect references.
R4 (parent R4): the C++ profile keeps classes, receivers and overloads unchanged.
R5 (parent R5): each profile reports its own Complete or Incomplete, reasons and limit text.
R6 (parent R6): no compiler is called by the scanner; dialect keywords are tolerated.
R7 (parent R7): header-language counts and per-language precision are verified on the pinned corpus.

## Constraints

C1, C2, C3, C4 of the initiative bind this epic.

## Done when

- Every File and Symbol of the pinned corpus has `language`; the Zephyr and autoas header counts match the independent counts.
- A C pack and a C++ pack print different reasons and limit text.
- `make cpp-check` reports precision per language.

## Boundaries

- Siblings: cross-language edges, `abi_exported` and the qualified Complete belong to epic-cross-language-boundaries; this epic adds the `language` and `linkage` it needs.
- Must not change: C++ symbols, edges and packs for a C++-only repository.

## References

- parent — `_bmad-output/initiative-language-profiles-and-boundaries/initiative-language-profiles-and-boundaries.md`, Requirements R1 to R7
- spec — `docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md`, §Language profiles
- decision — `docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md`, D7

## Notes

- Decision: 2026-11-16, the tracer is story 1 (`language` on every node): the thinnest path from scanner through graph to the ontology.
- Decision: 2026-11-16, story 5 (dialect keywords) is independent of 2 to 4 and can run in parallel after story 1.
