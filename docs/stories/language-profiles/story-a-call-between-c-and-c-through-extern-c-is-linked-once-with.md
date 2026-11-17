---
id: 2
type: story
title: "A call between C++ and C through extern \"C\" is linked once, with its mechanism named"
parent: epic-cross-language-boundaries
covers: [R8, R9, R10, R13]
after: [1, 1.2]
hitl: false
risk: high
---

# A call between C++ and C through extern "C" is linked once, with its mechanism named

## Description

Riskiest path of D8: the one resolver. Extractors emit boundary records; the resolver links an import to an export only when the ABI name is unique in the repository and both sides are in it; a dynamic lookup is unresolved. The first mechanism is `extern "C"` between C++ and C, which autoas already links (279 C++-to-C, 61 C-to-C++) under other rules and without a linkage flag. The record contract is in the ADR.

## Requirements

1. **A C++ call into a C function links with source `extern-c`** (R10)
   **Given** tests/fixtures/boundaries/extern_c: `lib.h` with the `extern "C"` guard declaring `lib_add`, `lib.c` defining it, `app.cpp` including `lib.h` and calling `lib_add`
   **When** the fixture is built
   **Then** `app.cpp::main` has a `CALLS` edge to `lib.c::lib_add` with `source` `extern-c`, confidence 0.9, `evidence_ref` `app.cpp:<line>`, and no second edge from an older rule for the same pair

2. **A C call into a C++ function defined with C linkage links the same way** (R13)
   **Given** `cb.cpp` defining `extern "C" int cb_run(void)` and `main.c` declaring and calling it
   **When** the fixture is built
   **Then** the edge from `main.c::main` to `cb.cpp::cb_run` has `source` `extern-c`

3. **A name that is not unique links nothing** (R8)
   **Given** two files each defining `extern "C" int dup(void)`
   **When** the fixture is built
   **Then** neither caller links; the call is unresolved with reason `ambiguous-abi-name`; the pack of `dup` is Incomplete

4. **A C++ name does not match a C name** (R8)
   **Given** `app.cpp` calling `foo(1.0)` where `foo(double)` is a C++ function without C linkage and `foo(int)` is a C function
   **When** the fixture is built
   **Then** no `extern-c` edge to the C `foo` is made

5. **A name defined outside the repository is not a boundary** (R8)
   **Given** `app.cpp` calling `strlen` and a vendor library function declared but not defined in the repository
   **When** the fixture is built
   **Then** no edge, no unresolved count and no boundary record is produced

6. **A dynamic lookup is unresolved and counted** (R9)
   **Given** `plug.c` calling `dlsym(h, name)` with a variable, and `dlsym(h, "lib_add")` with a literal
   **When** the fixture is built
   **Then** neither makes an edge; the enclosing Symbol has `incomplete_reasons` `dynamic-import`; the pack of `lib_add` states the repository's count of dynamic lookups

7. **A repository without a boundary builds the same graph** (R8)
   **Given** this repository, a Python fixture and the C++-only fixtures
   **When** `nodes.jsonl` and `edges.jsonl` are diffed before and after
   **Then** only the `language` and `linkage` properties differ

## Boundaries

- Must not change: C++ edges inside C++ files, C edges inside C files; the denylist.
- Out: literal `dlsym` links (counted unresolved here); a `source` of `jni`.
- Shared file: `cpp_graph.py` and the resolver's new module are owned by this story; stories 4 to 6 add mechanisms to the table, never rewrite it.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
