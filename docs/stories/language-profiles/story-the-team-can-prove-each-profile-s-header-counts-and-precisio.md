---
id: 6
type: story
title: "The team can prove each profile's header counts and precision on the corpus"
parent: epic-language-profiles
covers: [R7]
after: [2, 4]
hitl: true
risk: medium
---

# The team can prove each profile's header counts and precision on the corpus

## Description

Makes D7 provable on the corpus: header-language counts against an independent count, and precision and recall reported per language, so a C regression cannot hide behind C++ numbers. A person reviews the committed floors.

## Requirements

1. **Precision and recall are reported per language** (R7)
   **Given** the pinned corpus (cJSON, fmt, leveldb, autoas, Zephyr) and `bench/cpp/truth_clang.py` output for each
   **When** `make cpp-check` runs
   **Then** it prints, per repository and per language (`c`, `cpp`), call-edge precision, recall, the unmapped-end count and the indeterminate count, and exits 0 at or above the committed floors

2. **The truth parses each file as its own language, without devkb's decision** (R7)
   **Given** `truth_clang.py`
   **When** it parses `.c` with `-x c` and `.cc`, `.cpp`, `.cxx` with `-x c++`, and a header through its includer
   **Then** the output carries the language of each translation unit, and a test scans `truth_clang.py` for imports of `devkb` and finds none

3. **Header-language agreement is reported beside the counts, never folded in** (R2)
   **Given** the clang inclusion graph of Zephyr and autoas
   **When** `make cpp-check` runs
   **Then** it prints the share of headers whose devkb language equals the language of their includers' translation units, and lists the disagreeing headers

4. **A Complete C pack misses no determinate true caller** (R7)
   **Given** a sample of 100 C functions per repository (fixed seed, at least half with a name defined more than once)
   **When** `make cpp-check` runs
   **Then** every sampled symbol whose pack says Complete lists every determinate true caller site; any miss exits 1; the floor is 1.0

5. **A seeded wrong rule exits 1** (R7)
   **Given** a test that makes the C profile treat `static` as `extern` for its own run on tests/fixtures/profiles/c_linkage
   **When** the check runs
   **Then** it exits 1; no production flag injects the fault

6. **The floors are committed with their measurement** (R7)
   **Given** the first run
   **When** QA commits `floors` to `bench/cpp_corpus.json`
   **Then** each recall floor equals the first measurement minus 0.02, the initial precision floor is 0.95, and floors move up only

## Boundaries

- Must not change: `make gate-1` and `make gate-2` stay offline; the corpus check stays outside them (ADR-DKB-001 §7).
- Out: agent-cost or agent-quality measurement.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-language-profiles/epic-language-profiles.md
- spec — docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
