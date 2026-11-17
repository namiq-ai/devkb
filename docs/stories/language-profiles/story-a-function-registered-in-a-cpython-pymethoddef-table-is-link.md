---
id: 5
type: story
title: "A function registered in a CPython PyMethodDef table is linked to its Python caller"
parent: epic-cross-language-boundaries
covers: [R10, R14]
after: [4]
hitl: false
risk: medium
---

# A function registered in a CPython PyMethodDef table is linked to its Python caller

## Description

Python extension modules: a function listed in a `PyMethodDef` table is called from Python by the table's name on the module `PyInit_<name>` defines. Today such a function is an unexplained indirect reference, so its pack is Incomplete for the wrong reason.

## Requirements

1. **A table entry is an export under its Python name** (R14)
   **Given** tests/fixtures/boundaries/pyc_api: `calc.c` with `static PyObject *py_add(...)`, `static PyMethodDef methods[] = {{"add", py_add, METH_VARARGS, ""}, {NULL, NULL, 0, NULL}};` and `PyMODINIT_FUNC PyInit_calc(void)`; `use.py` with `import calc` and `def go(): return calc.add(1, 2)`
   **When** the fixture is built
   **Then** `py_add` has `abi_exported` true and `boundary_kind` `pyc-method` although it is `static`; the edge `use.py::go` to `calc.c::py_add` has `source` `pyc-api`

2. **The table reference no longer makes the pack Incomplete for the wrong reason** (R14)
   **Given** the same fixture
   **When** the pack of `py_add` is rendered
   **Then** its table reference is explained as an export (not counted as an unresolved indirect reference) and the pack is Complete for the languages read with the note; a second, unrelated reference to `py_add` still makes it Incomplete

3. **Aliases resolve, unknown modules do not** (R8)
   **Given** `import calc as c; c.add(1, 2)`, `from calc import add; add(1, 2)`, and `import other; other.add(1, 2)` where no `PyInit_other` exists
   **When** the fixture is built
   **Then** the first two link and the third is neither linked nor counted

4. **Two entries under one name link nothing** (R8)
   **Given** two tables in one module both listing `"add"`
   **When** the fixture is built
   **Then** no edge for `calc.add`; the call is unresolved with reason `ambiguous-abi-name`

## Boundaries

- Must not change: ctypes behavior of story 4.
- Out: `PyModuleDef` method tables built at runtime; Cython; `PyType_Spec` slots.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
