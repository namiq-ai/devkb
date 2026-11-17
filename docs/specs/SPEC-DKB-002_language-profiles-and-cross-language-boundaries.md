---
id: SPEC-DKB-002
title: "A coding agent gets a graph that knows C from C++ and follows a call across a language boundary"
type: specification
doc_type: prd
track: brownfield
status: accepted
created: 2026-11-16
updated: 2026-11-16
owner: PO
source: owner request 2026-11-16 (decisions D7 and D8)
supersedes: []
superseded_by: null
extends: SPEC-DKB-001
tickets: ["initiative-language-profiles-and-boundaries 1.1-1.6, 2.1-2.8", "backlog 1", "backlog 2"]
---

# SPEC-DKB-002: A coding agent gets a graph that knows C from C++ and follows a call across a language boundary

> **Draft — written by the PO in a non-interactive run from the owner's decisions D7 and D8.**
> Items tagged `Assumption:` are the PO's calls, not the owner's. Move `status` to `review` and `accepted` after the
> owner and TL read them. Nothing here is built.

**Requested by**: factory owner (decider and stakeholder)

Extends SPEC-DKB-001 and `docs/adr/ADR-DKB-001_c-cpp-support.md`. The decision record is `docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md`. The tickets are in `_bmad-output/initiative-language-profiles-and-boundaries/`; the requirement ids `R1` to `R17` below are the initiative's.

---

## Goals

- A pack for a C function is judged by C's rules and states C's limits; a pack for a C++ method is unchanged.
- A `.h` file is read as C or C++ by what it contains and what includes it.
- A call between C++ and C through `extern "C"`, from Python into C, and from C code to a Kconfig option is a graph edge, with its mechanism named.
- A pack for a symbol other languages may call says Complete for the languages read and says so; it never claims the strong Complete over callers it did not read.
- Every claim is measured: C and C++ against the compiler truth in `bench/cpp`, Python and C against labelled fixtures.

## Users

- Embedded and automotive engineers (Zephyr, AUTOSAR stacks) and mixed Python, C and C++ teams, and the coding agents working for them.
- devkb maintainers (BE, TL) and QA, who gate the release.
- The factory owner, who decides scope and the open questions below.

## Functional Requirements

Each line is an initiative requirement; its stories hold the runnable acceptance criteria.

- **R1** `language` (`c` or `cpp`) is on every C/C++ File and Symbol. Story 1.1.
- **R2** A `.h` file's language follows its contents and includers; an `extern "C"` guard marks a C header consumed by C++; default `c`. Story 1.2.
- **R3** The C profile resolves through linkage; function-pointer tables and ops structs are unresolved indirect references. Story 1.3.
- **R4** The C++ profile keeps classes, receivers and overloads. Stories 1.3, 1.4.
- **R5** Each profile reports its own Complete or Incomplete, reasons and limits. Story 1.4.
- **R6** No compiler in the scanner; dialect keywords are tolerated; the compiler is a verification flag. Story 1.5.
- **R7** Header counts and per-language precision are verified on the pinned corpus. Story 1.6.
- **R8** Extractors emit boundary records; one resolver links only a unique name with both sides in the repository. Stories 2.2, 2.4 to 2.6.
- **R9** A dynamic lookup is unresolved and counted. Stories 2.2, 2.4.
- **R10** A cross-language `CALLS` edge names its mechanism in `source` and carries a confidence; `CALLS_API` stays. Stories 2.2, 2.4 to 2.6.
- **R11** `abi_exported` and `boundary_kind` mark C-linkage non-`static` definitions and JNI and `PyInit_` names. Story 2.1.
- **R12** An exported symbol's pack is Complete for the languages read plus a note; a `static` symbol keeps the strong Complete. Stories 2.1, 2.4, 2.7.
- **R13** C++ and C through `extern "C"`: linkage flag, autoas counts hold. Stories 2.2, 2.3.
- **R14** Python and C: `ctypes`, `cffi`, `PyMethodDef`, pybind11 `m.def`. Stories 2.4 to 2.6.
- **R15** Kconfig and devicetree as `ConfigKey` with `READS` and `DECLARES`. Story 2.8.
- **R16** JNI is deferred as an edge; a JNI-named function is exported with `boundary_kind` `jni`. Story 2.1.
- **R17** Verification: compiler truth for C++ and C, fixtures with their own measure for Python and C. Stories 2.3, 2.7.

## Non-Functional Requirements

- `pyproject.toml` `dependencies` stays `["pyyaml>=6"]` and no compiler is invoked (ADR-DKB-001 D1).
- A repository with no foreign boundary builds `nodes.jsonl` and `edges.jsonl` identical to today's except the new `language` and `linkage` properties; Python and TypeScript output is unchanged.
- Zephyr builds in under 120 s and cJSON in under 5 s after the change (ADR-DKB-001 §7).
- Precision before recall: a link needs a unique name and both sides in the repository.
- A pack that says the strong Complete over a symbol with a foreign caller in a language the build read is a defect of the worst kind (`docs/BENCHMARK.md`); the Complete-recall floor stays 1.0.
- Fixtures are synthetic (RFC5737, RFC7042); no customer data.

## Out of Scope

- JNI edges and a Java scanner (0 Java files in the corpus); Rust, Go, C# and shell boundaries.
- A preprocessor, a compilation database, or any compiler call in devkb.
- Literal `dlsym(h, "x")` links (counted unresolved in this slice); `ctypes` callbacks passed to C; Cython; pybind11 class bindings; nanobind.
- Generated code and generators as graph (ticket `backlog 1`) and event-driven triggers and IPC (ticket `backlog 2`): filed as spikes, not built now.
- Agent-cost or agent-quality measurement.

## Context

- **Today the two languages are one.** `cpp_symbols.looks_cpp` reads a `.h` as C++ when its masked text holds `class`, `namespace`, `template` or `::`; `.c` is always C. `CXX_LIMITS_TEXT` is one text for every C/C++ pack and names overloads and receivers even for a C function (`cpp_symbols.py`, `packs.py`).
- **Calls already cross the C and C++ line, by accident of the rules.** A C++ file calling a C function links by the unique-free-function rule (`cpp-unique-free`, 0.6); autoas shows 279 C++-to-C and 61 C-to-C++ edges. Nothing marks the linkage, so a C++ overload with the same name can be told from a C function only by luck. `cpp_graph.py` writes `File`, `Symbol` and the edges; `cpp_resolve.py` holds the order; `process_api._coverage` turns `unresolved_calls` and `incomplete_reasons` into Complete or Incomplete (`packs.py` prints it).
- **The defect.** A C function `Java_demo_Calc_nativeAdd` (JNI-named) and a function called from Python through `ctypes` both get a pack saying Complete with their foreign callers missing: the extractor sees no call site, so `unresolved_calls` is 0. This is the owner's finding; the PO could not reproduce it in this run (the shell refused to create the fixture repository), so story 2.1's first criterion commits the failing test before any change.
- **The corpus.** Zephyr: 10,044 `.c`, 5,802 `.h` (2 with C++ constructs, 1,640 with an `extern "C"` guard), 70 C++ files, 56% of C files read a `CONFIG_*` option. autoas: 210 `.c`, 132 C++ files, 94 of 225 headers guarded.
- **Verification already exists for C and C++.** `bench/cpp/truth_clang.py` (libclang, independent of devkb) and `quality.py` (matches symbols by file, qualified name, then line containment; reports precision, recall, unmapped ends and honesty rate). Neither splits by language or edge `source`. Python and C has no truth yet.
- **`ConfigKey`** is documented as an environment variable or a root `pms.config.json` key, with `READS` (Symbol or File to ConfigKey) and `DECLARES` (File to ConfigKey) (`devkb/ontology.md`). Kconfig and devicetree widen its description; no node type or verb is added.
- **ADR numbering.** The code branch cites the C/C++ ADR as `ADR-DEVKB-008`; this repository files it as `ADR-DKB-001`. Same record.
- **Ontology rule.** A new property, edge `source` or `ConfigKey` use needs an Accepted ADR (`ADR-SDP-DEVKB-001`); ADR-DEVKB-009 is Proposed and must be Accepted before story 1.1 merges.

## Gaps

- GAP-1: no `language` on File or Symbol, so no per-language rule or message exists.
- GAP-2: the `.h` rule ignores includers and the `extern "C"` guard, and counts a lone `::` as C++.
- GAP-3: C is resolved by C++ rules (receivers, classes) and carries C++ limit text.
- GAP-4: no linkage flag, so `extern "C"` edges are unlabelled and not verifiable by mechanism.
- GAP-5: no boundary record, no cross-language resolver; Python-to-C and C-to-Python calls are invisible and their targets say Complete.
- GAP-6: a `PyMethodDef` table or pybind11 `m.def` is an unexplained indirect reference.
- GAP-7: Kconfig and devicetree options are not graph nodes; 56% of Zephyr C files depend on them invisibly.
- GAP-8: no per-language or per-mechanism precision measure; no Python-and-C truth.

## Approach

- GAP-1, GAP-2: story 1.1 writes `language`, `linkage`; story 1.2 implements the header order of ADR-DEVKB-009 §2. `Assumption:` the order is constructs outside `__cplusplus` guards, guard, includers all C++, else `c`; one include hop.
- GAP-3: story 1.3 gives C files their own resolution order (static in file, extern when unique); story 1.4 switches coverage and limit text by `language`.
- GAP-4, GAP-5: stories 2.1 and 2.2 add `linkage`-based `abi_exported`, `boundary_kind`, the record contract and the one resolver. `Assumption:` confidences `extern-c` 0.9, others 0.8.
- GAP-6: stories 2.5 and 2.6 read the tables and `m.def` as exports so their indirect reference is explained.
- GAP-7: story 2.8 reads `CONFIG_*` and Kconfig files into the existing `ConfigKey`. `Assumption:` key names `kconfig:CONFIG_FOO`, `devicetree:<label>`; `.conf` assignments out.
- GAP-8: stories 1.6, 2.3 and 2.7 extend `quality.py` and add `bench/boundaries/check.py` with a labelled truth.
- The honesty rule for exported symbols follows the owner: `abi_exported` is true for every non-static C-linkage definition. `Assumption:` kept as stated; story 2.7 measures how many C packs carry the note.

## Scope

Epic 1 — C and C++ are separate rule profiles that each report their own Complete (D7):

1. 1.1 Every File and Symbol says whether it is C or C++ — tracer
2. 1.2 A `.h` file is read as C or C++ by what it contains and what includes it
3. 1.3 A C function resolves through linkage, and a function-pointer table is unresolved
4. 1.4 A pack judges Complete by the rules of its symbol's own language
5. 1.5 The scanner reads dialect keywords and never calls a compiler
6. 1.6 The team can prove each profile's header counts and precision on the corpus

Epic 2 — A call that crosses a language is a graph edge, and an exported symbol says who may still call it (D8):

1. 2.1 A pack for an exported or JNI-named C function stops claiming the strong Complete — tracer, the defect fixture
2. 2.2 A call between C++ and C through `extern "C"` is linked once, with its mechanism named
3. 2.3 The team can prove `extern-c` edges against the compiler on autoas
4. 2.4 A Python call into a C library through `ctypes` or `cffi` is linked, a variable name is not
5. 2.5 A function registered in a CPython `PyMethodDef` table is linked to its Python caller
6. 2.6 A function bound by pybind11 `m.def` is linked to its Python caller
7. 2.7 The team can measure Python-and-C precision on fixtures
8. 2.8 A C file that reads `CONFIG_FOO` and the Kconfig file that declares it meet at one `ConfigKey`

Order: 1.1 first; 1.2, 1.3, 1.5 then run beside each other; 1.4 after 1.3; 1.6 after 1.2 and 1.4. Epic 2 waits on 1.1 and 1.4 (and 1.2 for 2.2); 2.1 first, 2.2 next (the riskiest path), then 2.3 and 2.4, then 2.5 and 2.6, then 2.7; 2.8 may run any time after 1.1.

Filed, not for now: `backlog` spike 1, generated code and pre-processing as graph; spike 2, event-driven triggers and communication.

## Assumptions and open questions

- Assumption: `language` is recorded on C/C++ nodes only; Python and TypeScript nodes get none, so their output is unchanged.
- Assumption: a function listed in a `PyMethodDef` table is `abi_exported` with `boundary_kind` `pyc-method` even when `static`.
- Assumption: no refactor sweep story; the owner can add one.
- Open question: limit the exported-symbol note to symbols declared in a header or named by an import record, to cut noise on C-only repositories (pick: not before story 2.7 measures it).
- Open question: a real Python and C corpus for the precision measure (pick: none yet; fixtures only).
- Open question: extractor and resolver module layout, for `bmad-architecture`.

---

## Original request

Decision D7 and decision D8 and the two further tickets of the owner's non-interactive brief of 2026-11-16 (language profiles over one scanner; one graph with per-language extraction and global resolution; generated code as graph; event-driven triggers). Evidence figures are the owner's.
