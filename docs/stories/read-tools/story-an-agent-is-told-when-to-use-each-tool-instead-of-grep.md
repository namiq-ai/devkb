---
id: 10
type: story
title: "An agent is told when to use each tool instead of grep"
parent: epic-core-read-tools
covers: [R1, R13]
after: [1, 6, 7, 8, 9]
hitl: false
risk: low
---

# An agent is told when to use each tool instead of grep

## Description

The tools only pay if the agent chooses them over grep. This story updates the MCP `INSTRUCTIONS`, the `devkb-lean-pack` skill and its `plugins/devkb` copy, the `devkb init` AGENTS block and the README, and pins toolset membership in one test (ADR-DEVKB-010 section 7). The wording follows the AGENTS.md table of this repository: ask by what you are about to do.

## Requirements

1. **Toolset membership is exact** (R1)
   **Given** `TOOLSETS` and a started MCP server per toolset
   **When** `pytest tests/test_readtools_wiring.py` runs
   **Then** `symbol`, `outline`, `uses` and `search_docs` are in `lean-pack`, `dev` and `all`, and in none of `core`, `workflow`, `docs`, `lean`

2. **Each instruction file names the four tools and the question each answers** (R13)
   **Given** `INSTRUCTIONS`, `skills/devkb-lean-pack/SKILL.md`, `plugins/devkb/skills/devkb-lean-pack/SKILL.md`, the `AGENTS_BLOCK` in `devkb/init.py`, `README.md`
   **When** the test greps each for the four tool names
   **Then** every file names all four, with a line of the form "where is X defined or what does it look like: `symbol`", "what is in this file: `outline`", "where does this name appear, including constants, macros and keys: `uses`", "what do the docs say: `search_docs`"

3. **The instructions say when grep is still right** (R13)
   **Given** the same files
   **When** they are read
   **Then** each says that `uses` is text and not complete, that a source reply with `end unknown` is a window, and that a miss on a name is not proof when the reply says so; the pack guidance of the skill is unchanged

4. **The two copies of the skill are identical and init is idempotent** (R13)
   **Given** `devkb init` run twice on a fresh repository
   **When** the resulting `AGENTS.md` and `CLAUDE.md` are compared
   **Then** the block appears once, the second run changes nothing, and the two skill files are byte-identical

5. **The tool count is reported where it is documented** (R13)
   **Given** the README's toolset table
   **When** the test compares it with `TOOLSETS`
   **Then** the listed tools and counts match

## Boundaries

- Must not change: the pack guidance and the measured `lean` arm.
- Not here: measuring whether agents obey (1.12).

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 7
