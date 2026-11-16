---
id: 6
type: story
title: "A function bound by pybind11 m.def is linked to its Python caller"
parent: epic-cross-language-boundaries
covers: [R10, R14]
after: [4]
hitl: false
risk: medium
---

# A function bound by pybind11 m.def is linked to its Python caller

## Description

pybind11: `m.def("name", &fn)` inside `PYBIND11_MODULE(mod, m)` exports the C++ function `fn` as `mod.name` to Python.

## Requirements

1. **A `m.def` of a function address links its Python caller** (R14)
   **Given** tests/fixtures/boundaries/pybind11: `bind.cpp` with `PYBIND11_MODULE(demo, m) { m.def("add", &add_ints); }` and `add_ints` defined once; `use.py` with `import demo` and `demo.add(1, 2)`
   **When** the fixture is built
   **Then** the edge from the Python caller to `add_ints` has `source` `pybind11`, confidence 0.8; `add_ints` has `boundary_kind` `pybind11`

2. **A lambda or an overload set is not guessed** (R9)
   **Given** `m.def("sub", [](int a, int b) { return a - b; })` and `m.def("mul", py::overload_cast<int, int>(&mul))` with two `mul` overloads
   **When** the fixture is built
   **Then** `demo.sub(...)` and `demo.mul(...)` produce no edge and are counted unresolved with reasons `lambda-binding` and `ambiguous-abi-name`

3. **Two `m.def` of one Python name link nothing** (R8)
   **Given** two `m.def("add", ...)` in one module
   **When** the fixture is built
   **Then** no edge for `demo.add`

4. **Class bindings are out and said so** (R14)
   **Given** `py::class_<K>(m, "K").def("go", &K::go)`
   **When** the pack of `K.go` is rendered
   **Then** it is not marked exported by pybind11 and the limit statement names class bindings as not read

## Boundaries

- Must not change: C++ call resolution; the `extern-c` mechanism.
- Out: `py::class_` methods, properties and enums; nanobind; Boost.Python.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/spec/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
