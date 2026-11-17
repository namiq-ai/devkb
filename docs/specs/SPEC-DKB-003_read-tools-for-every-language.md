---
id: SPEC-DKB-003
title: "A coding agent finds a symbol, a file's outline, a name's uses and a document's passage with one call instead of grep, in every language devkb reads"
type: specification
doc_type: prd
track: brownfield
status: accepted
created: 2026-11-16
updated: 2026-11-16
owner: PO
source: owner request 2026-11-16 (decisions D1 to D7); docs/analysis/read-tools-analysis.md
supersedes: []
superseded_by: null
extends: SPEC-DKB-001
tickets: ["initiative-read-tools-for-every-language 1.1-1.12, 2.1-2.7", "backlog 3", "backlog 4", "backlog 5"]
---

# SPEC-DKB-003: Read tools for every language

> **Draft: written by the PO in a non-interactive run from the owner's decisions D1 to D7.**
> Items tagged `Assumption:` are the PO's calls, not the owner's. Move `status` to `review` and `accepted` after the owner and TL read them. Nothing here is built.

**Requested by**: factory owner (decider and stakeholder)

The decision record is `docs/adr/ADR-DEVKB-010_read-tools.md`: it holds the data contract (reply fields, tier order, ranking, caps, capability flags, per-language promises) and the fixtures. This specification holds what is required and how it is accepted. The tickets are in `_bmad-output/initiative-read-tools-for-every-language/` (epics 1 and 2) and `_bmad-output/backlog/` (tickets 3, 4, 5); the ids `R1` to `R13` below are the initiative's.

---

## Goals

- An agent asks the graph where a name is defined, what is in a file, where a name appears and what the documents say, and gets a short, honest text answer instead of running grep and reading what it returns.
- The same four tools work on Python, TypeScript, JavaScript, C#, C, C++ and Odoo XML, and each states what it can promise there: exact range, or start only; found, or not indexed.
- A tool never states what it does not hold: no end line it lacks, no match below the similarity floor, no Complete over text.
- The saving is measured: fewer definition and outline greps, with no loss in the acceptance score.

## Users

- Coding agents working in any devkb-indexed repository (the lean-pack default).
- devkb maintainers (BE, TL) and QA, who gate the release; the owner, who decides scope and the open questions below.

## Functional Requirements

Each line is an initiative requirement; its stories hold the runnable acceptance criteria.

- **R1** (D1) The four tools exist as MCP tools in `lean-pack`, `dev` and `all`, and as `devkb symbol|outline|uses|docs`; replies are compact text and end with the staleness note when the graph is stale. Stories 1.1, 1.6, 1.8, 1.9, 1.10.
- **R2** (D2) `symbol` resolves in the tier order exact, qualified, suffix, glob, regex, prefix and substring, similar, stopping at the first tier with hits. Stories 1.1, 1.3.
- **R3** (D2) A fuzzy hit says `similar` with its score; below 55 the answer is "no symbol named X" with suggestions. Story 1.4.
- **R4** (D2) A match shows file, kind, line range, signature line, first docstring line, caller count and `how`; ties rank production first, shallower name, more callers, path; filters `kind`, `under`, `limit`. Stories 1.1, 1.5.
- **R5** (D3) `source=True` returns the range bounded at 80 lines (cap 200) with a "more lines" marker, an outline for a class that does not fit, `end unknown` and a 40-line approximate window when no end is stored, and `moved` when the signature no longer holds the name. Story 1.7.
- **R6** (D4) `outline` lists symbols in source order with nesting and the imports; directories, unique suffixes and unindexed files are handled. Story 1.6.
- **R7** (D5) `uses` lists definitions, then text matches by file and enclosing symbol, capped, labelled as text matches, never Complete. Story 1.8.
- **R8** (D6) `search_docs` returns documentation passages with their heading, specs and ADRs first, capped. Story 1.9.
- **R9** Each tool states per language what it can promise through one capability table; one test pins the table to the analysis matrix and one suite runs every tool on every language's fixture. Stories 1.2, 1.6, 1.7, 1.11, 2.1, 2.7.
- **R10** Where the graph lacks something (C# constructors, generic methods, interfaces; TypeScript class methods; shared overload nodes; start-line conventions; C macros and constants) the tool says what it cannot see and points to `uses`. Stories 2.1 to 2.5.
- **R11** (D7) On two new builds with the tools, definition and outline greps fall at least 60% with no loss in the acceptance score. Story 1.12.
- **R12** (D7) End-line floors are a repeatable check: Python and C# 99%, C and C++ 92%, TypeScript 95% after backlog 3. Story 2.6.
- **R13** Agent instructions, the lean-pack skill, the `devkb init` block and the README say when to use each tool instead of grep. Story 1.10.

## Non-Functional Requirements

- No new dependency: `pyproject.toml` `dependencies` stays `["pyyaml>=6"]`; no network and no LLM call (factory rule 1).
- No schema change: no node type, edge verb or Symbol property (`ADR-SDP-DEVKB-001`). The `language` property and a range flag are backlog 5, not for now.
- `nodes.jsonl` and `edges.jsonl` are byte-identical before and after the change on every fixture.
- A reply is under 6,000 bytes `[ASSUMPTION]`; a cap says what it cut.
- Files are read only inside the repository root; a `..` path is refused.
- `uses` and `search_docs` answer in under 1 s on a 5,000-file repository `[ASSUMPTION]`, measured, not guaranteed.
- Fixtures are synthetic; no customer data.

## Out of Scope

- Resolved references (who calls this by name text) beyond the existing `callers` and `pack`; `uses` is text and says so.
- Changing any extractor: TypeScript end lines (backlog 3), C# constructors, generic methods and interfaces (backlog 4), the `language` property and the range flag (backlog 5). Backlog 3 is a prerequisite only of the TypeScript floor and of flipping TypeScript to `exact`; the tools ship without it.
- Replacing `find_code`, `find_docs` or `pack`; they stay as they are.
- Searching untracked files, build output or external repositories.
- Agent-quality measurement beyond the D7 measure.

## Context

- **What agents grep for** (275 greps, nine builds, cost = text returned weighted by the calls still to come): where a name is defined 14.7% (90% then read the body with `-A/-B/-C`), outline of a file 11.9%, callers 11.7%, text in docs 9.6%, a module, import or key with no node 7.9%, a string in code 6.1%, tests 3.5%, a constant or macro 3.3%; filtering another command's output 30.1% is not a search. Definition plus outline is 27% of all grep cost.
- **What the graph holds.** `Symbol` nodes carry `kind`, `line_start`, `line_end`, `docstring_summary`; `CompactIndex.short` maps a short name to symbols and `sym_by_file` a file to its symbols. The old `ProcessAPI.symbol(name, limit)` is an exact short-name lookup returning JSON; `devkb symbol` calls it.
- **Where the end line is missing.** `build_symbols.py` writes TypeScript and JavaScript symbols with `line_end = line_start` (632 of 632 in mealie) although `ts_symbols._find_symbols` returns `body_end`; Odoo XML does the same. Python, C#, C and C++ store exact ends (92.8 to 100%).
- **Where names are missing.** TypeScript recall 0.58; C# misses 12.5% of methods and 29% of constructors and has no `interface` Symbols; overloads share one node in C# and C++; `line_start` is the name row for Python, C and C++ and sometimes the attribute or modifier row in C#.
- **How names match.** Real names, wrong case and a prefix are found by the cheap tiers; one typo needs edit similarity (96 to 99% at rank 1); two words of a name need word overlap; a missing name is wrongly accepted 35 to 50% of the time by word overlap with threshold 40, 1 to 7% by edit similarity at 55. 10 to 26% of short names map to several symbols.
- **Body sizes.** Up to 80 lines covers 97 to 99% of Python, 99% of C#, 96 to 98% of leveldb and fmt, 89% of cJSON.
- **The `language` property** is not on main; it exists only on the unmerged SPEC-DKB-002 branch, for C and C++ only. The tools therefore read capability from the file extension.
- **Existing code to build on** (read-only here, branch `feat/read-tools`): `mcp_server.py` (`TOOLSETS`, `INSTRUCTIONS`), `process_api.py` (`call`, `_resolve`, `find_code`, `_fit`, `TOOL_ARGS`, `TEXT_TOOLS`, `is_test_path`, `is_generated_path`, `Staleness`), `service.py` (`CompactIndex`, `KEEP_PROPS`), `ts_symbols.py`, `csharp_symbols.py`, `cpp_symbols.py`, `build_symbols.py`.

## Gaps

- GAP-1: no tool answers "where is X defined and what does it look like" in one call, in any language.
- GAP-2: no tool lists a file's symbols; agents grep for `def |class |function`.
- GAP-3: no tool finds a module, constant, macro or key; 11% of grep cost has no node.
- GAP-4: `find_docs` ranks documents by topic but returns no matching lines.
- GAP-5: TypeScript, JavaScript and Odoo XML ranges cannot bound source (backlog 3).
- GAP-6: C# constructors, generic methods and interfaces are not Symbols (backlog 4).
- GAP-7: no `language` property or range flag, so capability is inferred from the extension (backlog 5).
- GAP-8: shared overload nodes and start-line conventions can mislead a source reply.
- GAP-9: no measure of per-language range accuracy in the test suite, and the grep-purpose analysis has no "after" run.

## Approach

- GAP-1: story 1.1 (tracer) builds `symbol` exact with the staleness note and the shell command on FX-PY; 1.3 to 1.5 add the other tiers, the fuzzy floor and ranking; 1.7 adds source. The tiers are one pure function over `CompactIndex` so each tier is unit-testable.
- GAP-2: story 1.6.
- GAP-3: story 1.8; it scans tracked text, so it needs no schema change.
- GAP-4: story 1.9.
- GAP-5: story 2.1 makes the tools honest meanwhile; backlog 3 fixes the data. `[ASSUMPTION]` the capability table flips TypeScript and JavaScript to `exact` in backlog 3's own change.
- GAP-6, GAP-8: stories 2.2 to 2.4; backlog 4 fixes the data.
- GAP-7: story 1.2 builds the capability table; backlog 5 replaces its input.
- GAP-9: stories 1.11, 1.12 and 2.6.
- Order: 1.1 tracer, then 1.2 fixtures; 1.3, 1.6, 1.8, 1.9 run beside each other; 1.4 and 1.5 after 1.3; 1.7 after 1.6; 1.10 after the tools; 1.11 after 1.10; 1.12 last. Epic 2 waits on 1.2 and 1.7 and runs beside the rest of epic 1.

## Scope

Epic 1: An agent finds a symbol, a file's outline, a name's uses and a document's passage with one call instead of grep (D1 to D7).

1. 1.1 `symbol` answers an exact name with file, range, signature, callers and the staleness note: tracer
2. 1.2 Six fixture repositories pin the expected answers for every language
3. 1.3 `symbol` finds a qualified name, a suffix, a glob or a regular expression
4. 1.4 `symbol` offers similar names without ever accepting a wrong one
5. 1.5 `symbol` ranks symbols that share a name and filters by kind and path
6. 1.6 `outline` shows a file's symbols in order, with its imports
7. 1.7 `symbol` returns the source of its range, bounded, and never states an end it does not have
8. 1.8 `uses` shows where a name appears as text, grouped by the symbol that holds it
9. 1.9 `search_docs` returns the best documentation passages, specs and ADRs first
10. 1.10 An agent is told when to use each tool instead of grep
11. 1.11 Every tool answers on every language's fixture as the promise table says
12. 1.12 The team can show that agents grep less for definitions and outlines with no loss in score

Epic 2: Each language's tools say only what its graph holds, and what it cannot see.

1. 2.1 A TypeScript, JavaScript or Odoo XML symbol is shown from its start, and missing class methods are named
2. 2.2 A C# constructor, generic method or interface that is not a Symbol is named, not denied
3. 2.3 Overloads that share one node say so
4. 2.4 A C# symbol whose range starts at attributes still shows its signature line
5. 2.5 A C macro, constant or key that is not a Symbol is pointed to `uses`
6. 2.6 The per-language end-line floors are a repeatable check
7. 2.7 A name defined in two languages shows each match under its own language's promise

Filed separately, not part of the initiative: `backlog 3` TypeScript and JavaScript symbols store their real end line (prerequisite of the TypeScript floor); `backlog 4` C# constructors, generic methods and interfaces become Symbols (not for now); `backlog 5` the `language` property and the capability flag `range` on every Symbol (not for now).

## Assumptions and open questions

- Assumption: the old `symbol` JSON method and `devkb symbol NAME` are replaced by the new text tool; tier 1 keeps their behaviour (ADR section 7).
- Assumption: capability comes from a file-extension table until backlog 5 (ADR section 1).
- Assumption: word overlap proposes candidates and edit similarity at 55 or more accepts (ADR section 3.2, open question 1).
- Assumption: auto-detected regex needs one of `^ $ + ( ) [ ] { } |` or a backslash; a dot, colon or hash means a qualified name.
- Assumption: caller count is direct callers, one hop; the score is the edit similarity of lower-cased short names, 0 to 100; suggestions list up to 5 names; the byte budget is 6,000.
- Assumption: `uses` searches tracked files (`git ls-files`), skips generated paths, files over 1 MB and binaries.
- Assumption: a `moved` symbol returns no source; the reply names `uses`.
- Assumption: the grep-purpose script `bench/exercises/cpp/grep_purposes.py` and the nine transcripts are not in this checkout; story 1.12 starts by finding them (`range_accuracy.py` and `name_matching.py` exist).
- Assumption: no refactor sweep story; twelve stories in epic 1, the owner can add one.
- Open question: should `symbol` return source for more than the first match? Pick: no.
- Open question: should `find_code` leave the `dev` toolset once `symbol` is measured? Pick: not before story 1.12.
- Open question: a real C# corpus with generics-heavy code for the 99% floor; MediatR and FluentValidation are the corpus used so far.

---

## Original request

Decisions D1 to D7 of the owner's non-interactive brief of 2026-11-16 (four read tools, the tiered name resolver, bounded source, outline, uses, doc search, the success measure) and the four tickets to file separately. Figures are from `docs/analysis/read-tools-analysis.md`.
