---
tracker_id: ""
id: 2
type: epic
title: "A call that crosses a language is a graph edge, and an exported symbol says who may still call it"
parent: initiative-language-profiles-and-boundaries
covers: [R8, R9, R10, R11, R12, R13, R14, R15, R16, R17]
sources: []
companions: []
after: []
refined: true
risk: high
---

# A call that crosses a language is a graph edge, and an exported symbol says who may still call it

## Description

Decision D8. Each extractor emits boundary records; one resolver matches them. The first target is C++ and C through `extern "C"`: autoas already links 279 C++-to-C and 61 C-to-C++ edges, but under same-file or unique-name rules and without a linkage flag. Then Python and C, then Kconfig and devicetree options. The defect that opens the epic: a C function `Java_demo_Calc_nativeAdd` (JNI-named) and a function called from Python through `ctypes` both get a pack saying Complete with their foreign callers missing.

## Outcome

An agent asking who calls a C function sees its C, C++ and Python callers when the graph can prove them, and a plain note when callers may exist in a language not read.

## Requirements

R8 (parent R8): extractors emit boundary records; one resolver matches them only when the name is unique and both sides are in the repository.
R9 (parent R9): a dynamic case is counted as unresolved, never guessed.
R10 (parent R10): a cross-language `CALLS` edge carries `source` naming the mechanism and a confidence; `CALLS_API` stays for network boundaries.
R11 (parent R11): a C-linkage non-`static` definition, or a JNI or `PyInit_` name, gets `abi_exported` and `boundary_kind`.
R12 (parent R12): an exported symbol's pack is Complete for the languages read plus a note; a `static` symbol keeps the strong Complete.
R13 (parent R13): C++ and C through `extern "C"` link with the linkage flag, and the autoas edge counts hold.
R14 (parent R14): `ctypes`, `cffi`, `PyMethodDef` and pybind11 `m.def` link Python and C.
R15 (parent R15): Kconfig and devicetree options are `ConfigKey` with `READS` and `DECLARES`.
R16 (parent R16): a JNI-named function is exported with `boundary_kind` `jni`; no JNI edge.
R17 (parent R17): C++ and C edges are verified against compiler truth; Python and C on fixtures with their own precision measure.

## Constraints

C1 to C5 of the initiative bind this epic.

## Done when

- The defect fixture's two packs carry the foreign-callers note; the Python caller is listed in the ctypes-called function's pack.
- `quality.py` reports `extern-c` precision at or above the committed floor on autoas, and the 279 and 61 counts hold.
- The Python and C fixture check reports precision 1.0 with every dynamic case unresolved.
- A Zephyr C file's pack lists the `ConfigKey`s it reads and the Kconfig file declaring each.

## Boundaries

- Siblings: `language` and `linkage` properties and per-profile coverage belong to epic-language-profiles.
- Out: JNI edges, a Java scanner, other languages, network boundaries (`CALLS_API` unchanged).
- Touch point: `bench/cpp` — compiler truth; owner: this epic, story 3.

## References

- parent — `_bmad-output/initiative-language-profiles-and-boundaries/initiative-language-profiles-and-boundaries.md`, Requirements R8 to R17
- spec — `docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md`, §Boundaries
- decision — `docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md`, D8

## Notes

- Decision: 2026-11-16, the tracer is story 1: the defect fixture's packs, before any edge exists. It proves the riskiest wording path (a qualified Complete) with no resolver.
- Decision: 2026-11-16, Kconfig (story 8) is independent of the resolver and may run any time after story 1.
- Open question: the extractor module layout and the shape of a boundary record in code are for `bmad-architecture`; the contract is in the ADR.
