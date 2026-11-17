---
id: 8
type: story
title: "A C file that reads CONFIG_FOO and the Kconfig file that declares it meet at one ConfigKey"
parent: epic-cross-language-boundaries
covers: [R15]
after: [1.1]
hitl: false
risk: medium
---

# A C file that reads CONFIG_FOO and the Kconfig file that declares it meet at one ConfigKey

## Description

Kconfig and devicetree options are the largest hidden dependency of embedded C: 56% of Zephyr's C files read a `CONFIG_*` option. The existing `ConfigKey` node with `READS` and `DECLARES` edges gets a second source, so a C file and the Kconfig file declaring the option meet at one node. No node type and no verb is added.

## Requirements

1. **A C file's read and a Kconfig declaration meet at one ConfigKey** (R15)
   **Given** tests/fixtures/boundaries/kconfig: `Kconfig` with `config FOO` and `config FOO_BUF_SIZE`, and `drivers/foo.c` using `#if defined(CONFIG_FOO)`, `IS_ENABLED(CONFIG_FOO)`, `#ifdef CONFIG_FOO` and `CONFIG_FOO_BUF_SIZE`
   **When** the fixture is built
   **Then** `ConfigKey` `kconfig:CONFIG_FOO` has a `DECLARES` edge from `Kconfig` and a `READS` edge from `drivers/foo.c` (from the Symbol when inside a function, else from the File), each with `evidence_ref` `<path>:<line>`

2. **An undeclared option is still a read** (R15)
   **Given** `CONFIG_BAR` read in `drivers/foo.c` with no Kconfig entry in the repository
   **When** the fixture is built
   **Then** `kconfig:CONFIG_BAR` has a `READS` edge and no `DECLARES`, and its pack says it is not declared in the repository

3. **Comments, strings and `#if 0` read nothing** (R15)
   **Given** `CONFIG_BAZ` only in a comment, a string and an `#if 0` block
   **When** the fixture is built
   **Then** no `ConfigKey` for it exists

4. **A devicetree label meets its reader** (R15)
   **Given** `board.dts` with `foo: node@0 {}` and `drivers/foo.c` using `DT_NODELABEL(foo)`
   **When** the fixture is built
   **Then** `devicetree:foo` has `DECLARES` from the `.dts` file and `READS` from the C file

5. **The corpus matches an independent count** (R15)
   **Given** the pinned Zephyr clone
   **When** `python3 bench/cpp/config_counts.py REPO` (a regex count importing nothing from `devkb`) and `devkb build` both run
   **Then** the share of C files with at least one `READS` to a `kconfig:` key is within two points of the independent share (the owner's figure is 56%), and Zephyr still builds in under 120 s

6. **Existing ConfigKey behavior is unchanged** (R15)
   **Given** the environment-variable and `pms.config.json` tests
   **When** they run
   **Then** they pass unchanged, and `git diff -- devkb/ontology.md` is limited to the `ConfigKey` description

## Boundaries

- Must not change: environment-variable `ConfigKey`s; values are never stored.
- Out: `.conf` and `prj.conf` assignments; resolving which option is enabled in a build; devicetree property reads beyond node labels.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-cross-language-boundaries/epic-cross-language-boundaries.md
- spec — docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
