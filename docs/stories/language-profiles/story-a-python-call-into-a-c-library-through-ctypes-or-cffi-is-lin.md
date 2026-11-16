---
id: 4
type: story
title: "A Python call into a C library through ctypes or cffi is linked, a variable name is not"
parent: epic-cross-language-boundaries
covers: [R9, R10, R14]
after: [2]
hitl: false
risk: medium
---

# A Python call into a C library through ctypes or cffi is linked, a variable name is not

## Description

Second target of D8: Python calling a C library. The Python side emits an import record for `lib.name(...)` where `lib` is provably a `ctypes` or `cffi` library handle; the C side already exports. A name held in a variable is dynamic and stays unresolved.

## Requirements

1. **A `ctypes` call links to the C function with source `ctypes`** (R14)
   **Given** tests/fixtures/boundaries/ctypes: `use.py` with `lib = ctypes.CDLL("./libcalc.so")` and `def go(): return lib.add_ints(1, 2)`, `calc.c` defining `add_ints`
   **When** the fixture is built
   **Then** the edge `use.py::go` to `calc.c::add_ints` has `source` `ctypes`, confidence 0.8; `callers add_ints` lists `go`

2. **`cffi` links the same way** (R14)
   **Given** `ffi.cdef("int add_ints(int, int);")`, `lib = ffi.dlopen("calc")`, `lib.add_ints(1, 2)`
   **When** the fixture is built
   **Then** the edge has `source` `cffi`

3. **A receiver that is not a library handle is not a boundary** (R8)
   **Given** `obj.add_ints(1, 2)` where `obj` is not bound to `CDLL`, `cdll.LoadLibrary` or `ffi.dlopen`
   **When** the fixture is built
   **Then** no edge and no unresolved count result

4. **A name held in a variable is unresolved** (R9)
   **Given** `getattr(lib, name)(1, 2)` with a variable `name`
   **When** the fixture is built
   **Then** no edge; the Python Symbol has `incomplete_reasons` `dynamic-import`; the repository count in the exported symbols' packs grows by one

5. **A `static` C function and a duplicated name are never targets** (R8)
   **Given** `lib.helper(...)` where `helper` is `static` in `calc.c`, and `lib.dup(...)` where `dup` is non-static in two C files
   **When** the fixture is built
   **Then** neither links

6. **The note of story 1 now lists the Python caller** (R12)
   **Given** the defect fixture
   **When** the pack of `add_ints` is rendered
   **Then** `go` is listed as a caller with the mechanism `ctypes`, and the note still says callers may exist in languages not read

## Boundaries

- Must not change: Python-to-Python resolution; `CALLS_API`.
- Out: `argtypes` and `restype` declarations (read as neither call nor reference); `ctypes` callbacks passed to C.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/spec/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
