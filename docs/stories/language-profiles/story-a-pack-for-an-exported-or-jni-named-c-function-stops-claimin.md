---
id: 1
type: story
title: "A pack for an exported or JNI-named C function stops claiming the strong Complete"
parent: epic-cross-language-boundaries
covers: [R11, R12, R16]
after: [1.1, 1.4]
hitl: false
risk: medium
---

# A pack for an exported or JNI-named C function stops claiming the strong Complete

## Description

Tracer for D8, and the fix for its defect. Before any edge exists, a C function that other languages may call must stop getting the strong Complete. This story adds `abi_exported`, `boundary_kind` and the qualified wording, and proves it on the defect fixture.

## Requirements

1. **The defect is shown first** (R12)
   **Given** tests/fixtures/boundaries/defect holds `calc.c` (`Java_demo_Calc_nativeAdd`, `add_ints`, `static int local_sum`, `PyInit_calc`) and `use.py` (`lib = ctypes.CDLL("./libcalc.so")`, `lib.add_ints(1, 2)`)
   **When** the test runs against the code before this story
   **Then** the packs of `Java_demo_Calc_nativeAdd` and `add_ints` say Complete with no note, and the test is committed first as expected-failing

2. **A JNI-named function is exported and its pack is qualified** (R11)
   **Given** the defect fixture
   **When** `devkb pack --project tests/fixtures/boundaries/defect file calc.c` runs
   **Then** `Java_demo_Calc_nativeAdd` has `abi_exported` true and `boundary_kind` `jni`; its pack says Complete for the languages read (`c`, `python`) and that callers may exist in languages not read; it does not print the strong sentence

3. **A non-static C function and a `PyInit_` function are exported** (R11)
   **Given** the defect fixture
   **When** the graph is read
   **Then** `add_ints` has `abi_exported` true, `boundary_kind` `c-abi`; `PyInit_calc` has `boundary_kind` `pyinit`; both packs carry the note

4. **A `static` function keeps the strong Complete** (R12)
   **Given** `static int local_sum` called in `calc.c`
   **When** its pack is rendered
   **Then** the pack is today's strong Complete and has no note; `abi_exported` is absent or false

5. **C linkage inside a C++ file is exported, a C++ method is not** (R11)
   **Given** `wrap.cpp` with `extern "C" int wrap_add(int, int) { ... }` and a class method `Calc::add`
   **When** the graph is read
   **Then** `wrap_add` has `language` `cpp`, `linkage` `c`, `abi_exported` true; `Calc.add` has neither `abi_exported` nor a note

6. **The reply carries the qualifier as data** (R12)
   **Given** `callers add_ints`
   **When** the JSON is read
   **Then** it has `complete` true, `qualified` true, `languages_read` listing the languages the build read, and `boundary_kind`

7. **Python and C++ packs of non-exported symbols are unchanged** (R12)
   **Given** the existing pack tests
   **When** they run
   **Then** they pass unchanged

## Boundaries

- Must not change: Python symbol packs; the Incomplete wording and reasons.
- Out: any boundary edge (stories 2 to 6); a JNI edge (deferred).

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/spec/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
