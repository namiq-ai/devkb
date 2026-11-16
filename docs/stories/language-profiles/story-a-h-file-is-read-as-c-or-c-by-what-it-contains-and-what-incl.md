---
id: 2
type: story
title: "A .h file is read as C or C++ by what it contains and what includes it"
parent: epic-language-profiles
covers: [R2]
after: [1]
hitl: false
risk: medium
---

# A .h file is read as C or C++ by what it contains and what includes it

## Description

A `.h` file is the one place C and C++ share a path. Today `looks_cpp` calls it C++ when it holds `class`, `namespace`, `template` or `::`, and ignores who includes it and the `extern "C"` guard. This story implements the rule order of ADR-DEVKB-009 D7.

## Requirements

1. **C++ constructs outside a `__cplusplus` guard make a header C++** (R2)
   **Given** tests/fixtures/profiles/headers holds `ns.h` (a `namespace`), `tpl.h` (a `template`), `cls.h` (a `class` with `public:`), each outside any `#ifdef __cplusplus`
   **When** the fixture is built
   **Then** each File has `language` `cpp`

2. **An `extern "C"` guard marks a C header consumed by C++** (R2)
   **Given** `guarded.h` whose only C++ is `#ifdef __cplusplus` / `extern "C" {` / `#endif`, declaring plain C functions
   **When** the fixture is built
   **Then** `language` is `c` and the File has `consumed_by_cpp` true
   **And** a class defined inside the `#ifdef __cplusplus` region does not make it `cpp`

3. **The includers decide an unguarded header with no C++ construct** (R2)
   **Given** `only_cpp.h` included by `.cpp` files only, `mixed.h` included by one `.c` and one `.cpp`, and `lonely.h` included by nothing
   **When** the fixture is built
   **Then** `only_cpp.h` is `cpp`, `mixed.h` is `c`, `lonely.h` is `c`

4. **Words in comments and strings and a lone `::` decide nothing** (R2)
   **Given** a header with `class` and `namespace` only in a comment and a string, and another whose only hint is `::` in a macro argument
   **When** the fixture is built
   **Then** both are `c`

5. **The counts match an independent count on the corpus** (R2)
   **Given** the pinned Zephyr and autoas clones
   **When** `python3 bench/cpp/header_counts.py REPO` (a regex count that imports nothing from `devkb`) and `devkb build` both run
   **Then** Zephyr shows 5,802 `.h`, 2 with C++ constructs, 1,640 guarded; autoas shows 94 of 225 guarded; and devkb's counts equal the independent counts, with every differing file listed

## Boundaries

- Must not change: symbol extraction inside a header (only the language label and the reading mode follow it).
- Out: transitive includers beyond one hop; includes resolved through a compilation database.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-language-profiles/epic-language-profiles.md
- spec — docs/spec/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
