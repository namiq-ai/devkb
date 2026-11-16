---
id: 5
type: story
title: "The scanner reads dialect keywords and never calls a compiler"
parent: epic-language-profiles
covers: [R6]
after: [1]
hitl: false
risk: low
---

# The scanner reads dialect keywords and never calls a compiler

## Description

Embedded C is full of compiler dialect: `__attribute__`, IAR and ARM keywords. The scanner must read definitions that carry them without calling a compiler; the compiler appears only in the flags of the verification run (`truth_clang.py`).

## Requirements

1. **A definition with a dialect keyword is found with its proving line** (R6)
   **Given** tests/fixtures/profiles/dialect defines functions with `__attribute__((section(".ram")))`, `__interrupt`, `__irq`, `__ramfunc`, `__root`, `__weak`, `__packed`, `__svc(0)` and `__asm__ volatile` bodies
   **When** the fixture is built
   **Then** each function is a Symbol, and the text at its `line_start` contains its name

2. **Dialect text is not read as a call or a definition** (R6)
   **Given** `__attribute__((aligned(4)))` and `__asm__("nop")` inside function bodies
   **When** the fixture is built
   **Then** no Symbol or call named `aligned`, `__attribute__` or `__asm__` exists

3. **The tolerated keywords live in one table** (R6)
   **Given** the change
   **When** the table is read
   **Then** a keyword is added only with a fixture line, and a test fails for a table entry no fixture uses

4. **The scanner never invokes a compiler** (R6)
   **Given** `devkb/`
   **When** `pytest tests -k no_compiler` runs
   **Then** a scan of the sources finds no `subprocess` call to `gcc`, `clang`, `cc`, `armcc` or `iccarm`, and `pyproject.toml` `dependencies` is `["pyyaml>=6"]`

5. **The compiler appears only as verification flags** (R6)
   **Given** `bench/cpp/truth_clang.py`
   **When** it is run with `-D__interrupt= -D__ramfunc=`
   **Then** it accepts the flags and parses the dialect fixture's translation units

## Boundaries

- Out: parsing assembly, linker scripts or IDE project files.
- Must not change: the C++ extractor's reading of `[[attributes]]`.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-language-profiles/epic-language-profiles.md
- spec — docs/spec/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
