---
id: 1
type: spike
title: "How does the graph record input, generator and output, so that a pack over generated code says what it cannot see?"
parent: none
covers: []
after: []
assignee: ""
refined: false
hitl: true
risk: medium
---

# How does the graph record input, generator and output, so that a pack over generated code says what it cannot see?

## Description

**Not for now.** Filed 2026-11-16 by the owner's request; nothing here is built until the owner starts it. It follows SPEC-DKB-002 and uses its `language`, `linkage` and boundary resolver; it does not wait for them to be written, but its prototype does.

**Who is blocked and why.** An agent asking `pack` about a C function in Zephyr or autoas gets Complete although part of the code it depends on is not in git and is written by a program that is not C. The graph reads only tracked C/C++ text, so calls and macros defined in a generated header are invisible, and a pack says Complete over them.

**Evidence** (counts from the owner's survey of the two corpora, to be re-run at the pinned commits in step 1):

| What | Zephyr | autoas |
|---|---|---|
| Python files that write `.h` or `.c` | 41 generator scripts | 32 |
| CMake files running a generator (`add_custom_command`, `execute_process`) | 159 | not counted |
| `configure_file` | 15 | not counted |
| template inputs (jinja, `.in`, `.tmpl`) | 18 | 12 |
| C files including a generated header that is not in git (`autoconf.h`, `devicetree_generated.h`, syscall lists) | 394 | not counted |
| files using devicetree macros | 4,955 | |
| files using Kconfig in `#if` or `IS_ENABLED` | 4,546 | |
| cJSON: share of real call edges that exist only through macro expansion | 65% | |

**The question.** How do we graphify input, generator, output, and how does a pack state it? The proposed answer, to confirm or replace:

- **GENERATES**: an edge from the generator (a Python script, a CMake file, a template renderer) to the `File` it writes. Evidence is the `OUTPUT` or `BYPRODUCTS` list of an `add_custom_command`, the `configure_file(in out)` pair, or the write call (`open(path, "w")`, `Path.write_text`) with a literal path. A path built from a variable is not linked; it is counted as an unresolved generator output.
- **Inputs** are a property of that edge (`inputs`: the generator's declared `DEPENDS`, `configure_file` input, or a template file), not a second verb, to keep the ontology small.
- An `#include` of a path that no tracked file has is recorded on the including `File` as an unresolved **generated dependency** naming the generator when a `GENERATES` edge matches the path, else `generator: unknown`.
- A pack over a symbol in such a file says **Incomplete (generated dependency)**, lists the generated paths and their generators, and says macros and calls defined there are not seen. The existing reasons set gains `generated-dependency`; the Complete rule of SPEC-DKB-001 is otherwise unchanged.

## Approach

1. Re-run the survey above at the pinned commits (Zephyr, autoas) with a script that imports nothing from `devkb`; commit the counts. Time box for the whole spike: 3 days `[ASSUMPTION]`.
2. Prototype, on a branch and without a merge, the three evidence readers: CMake (`OUTPUT`, `BYPRODUCTS`, `configure_file`), Python write calls, templates. Table-driven: one row per pattern, a row added only with a fixture.
3. Decide, with numbers, the questions below. Each answer goes in the ADR draft.
   - Is a missing generated include a **file-level** reason, or **symbol-level** (only a symbol whose body uses an identifier defined nowhere in tracked source, in a file that includes a generated header)? File-level flags 394 Zephyr files; symbol-level is narrower but needs a name table.
   - Does a generated output that a build tree already holds (a file present but untracked) get read? Today untracked and `build/` paths are skipped; reading a build tree needs a flag and a stated staleness limit.
   - How are Kconfig and devicetree tied in? `autoconf.h` is generated from Kconfig and `devicetree_generated.h` from `.dts`; SPEC-DKB-002 story 2.8 gives `ConfigKey` nodes, so a `GENERATES` edge from the generator, plus `READS` and `DECLARES`, connects an option to the header that carries it.
   - Macro expansion (cJSON's 65%) is a separate limit (SPEC-DKB-001 Out of Scope). State whether this ticket touches it; the pick is no, and the pack names it.
   - A new edge verb `GENERATES` and new reason `generated-dependency` need an Accepted ADR (`devkb/ontology.md`, ADR-SDP-DEVKB-001).
4. Render the pack wording for three fixtures: generated header included, generated header present in the build tree, generator with a variable output path.
5. TL and the owner review the ADR draft; the owner decides whether to build.

## Acceptance Criteria

1. **The survey is reproducible and its counts are committed**
   Verify: `python3 bench/generated/survey.py ZEPHYR_DIR AUTOAS_DIR` prints the counts of the table above; the output is in the spike's result file.
2. **The prototype finds generator-to-output edges, with a measured false-link rate**
   Verify: on a hand-labelled sample of 30 generator outputs across Zephyr and autoas, the result file shows linked, wrongly linked, unlinked and counted-unresolved (a variable path) separately; a wrong link is a failure of the model, not a footnote.
3. **A generated include names its generator**
   Verify: the result file gives, for the 394 Zephyr files, the share whose include resolves to a named generator and the share left `generator: unknown`, with the unknown paths listed.
4. **The pack states it**
   Verify: three rendered packs (fixtures in `tests/fixtures/generated/`) show Incomplete with reason `generated-dependency`, the paths and the generators; a Python pack and a pack in a file with no generated include are unchanged.
5. **The answers to the five questions of step 3 are recorded with their consequences**
   Verify: an ADR draft `docs/adr/ADR-DEVKB-0NN_generated-code-as-graph.md` with status Proposed.
6. **The people who must accept it have**
   Verify: TL and the owner, recorded in the ADR's status line.

## References

- spec — `docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md`, §Context, Gaps and Approach (the ConfigKey and boundary resolver this builds on)
- decision — `docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md`
- spec — `docs/specs/SPEC-DKB-001_a-coding-agent-working-in-a-c-or-c-repository-ge.md`, Out of Scope (preprocessor) and Gaps
- ontology — `devkb/ontology.md` (read in the code branch `<local-path>`)
- sibling — `_bmad-output/backlog/spike-event-driven-triggers-and-communication.md` (autoas RTE and Zephyr syscall lists are both generated and registered)

## Notes

- Assumption: time box 3 days; pick, the owner may change it.
- Assumption: the verb is `GENERATES` as the owner named it; the inputs ride on the edge as a property.
- Open question: is a build tree (`build/`, `zephyr/include/generated`) ever read? Pick: no in this spike; the pack names the generator and the missing file instead.
- Open question: the survey counts are the owner's; the "not counted" cells for autoas need a number before the criteria are final.
