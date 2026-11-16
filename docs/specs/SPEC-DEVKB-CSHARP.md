---
id: SPEC-DEVKB-CSHARP
title: "C# support: definitions, calls and tests in the graph"
type: spec
status: proposed
created: 2026-11-16
story: "#32"
---

# C# support

Written with the ODSF lifecycle's BMAD roles: the analyst's brief (§1), the product requirements (§2), the
architecture (§3) and the story (§4), checked against ODSF's readiness gate (§5). Implementation used devkb on its own
code (§6).

## 1. Brief (analyst)

**Problem.** A user who saw the launch wrote that they work in C# and so cannot use devkb (#25). They are right:
devkb reads Python fully and TypeScript/JavaScript partly; for every other language it records only files and git
history. On MediatR (160 `.cs` files, 13,996 lines, 39 test files) `devkb build` produces 4 nodes and no code at all
(#32, Evidence).

**Who.** Developers in C# codebases using Claude Code, Codex or Cursor: enterprise services (ASP.NET), desktop, Unity
games. C# is among the most used languages in professional development; without it devkb excludes most .NET teams.

**What matters to them.** The same answers devkb gives in Python, for the questions the benchmark showed it saves on:
who calls this method (at any depth), what breaks if it changes, which test methods reach it, each with a proof line,
and an honest statement when the graph could not see something.

**C# facts that shape the design.**

| Fact | Consequence |
|---|---|
| Namespaces are block (`namespace A { }`) or file-scoped (`namespace A;`, C# 10) | both forms set the scope |
| Types: `class`, `struct`, `interface`, `record`, `record struct`, `enum`, generic (`Foo<T>`), `partial` across files | all are `kind: class` (enum: `enum`); a partial type is one name in several files |
| Members: methods, constructors, properties with accessor bodies, expression-bodied members (`=> expr;`), local functions, operators, indexers | expression-bodied members end at `;`, not at a brace |
| Strings: regular, verbatim (`@"..."` with `""`), interpolated (`$"...{x}..."`), raw (`"""..."""`, C# 11) | all masked before reading braces, or a `{` inside a string breaks the scope stack |
| Calls: `Name(`, `obj.Name(`, `Type.Name(` (static), `this.`/`base.`, `new Type(`, generic `Name<T>(`, extension methods `x.Ext()` | resolved only where one target fits |
| Tests: xUnit `[Fact]`, `[Theory]`; NUnit `[Test]`, `[TestCase(...)]`, `[TestCaseSource]`; MSTest `[TestMethod]`, `[DataTestMethod]`; projects named `*.Tests`, files `*Tests.cs` | test methods are found by attribute; test files by project or file name |
| Generated code: `*.g.cs`, `*.Designer.cs`, `obj/`, `bin/` | skipped |

## 2. Requirements (PM)

**Functional.**

| # | Requirement |
|---|---|
| F1 | `devkb build` adds a `Symbol` for each class, struct, interface, record, enum, method, constructor, property (with an accessor body or expression), operator and local function in tracked `.cs` files, keyed `path::Namespace.Type.Member`, with `line_start`, `line_end` and `DEFINED_IN` its file |
| F2 | `CALLS` edges between those symbols, each with an evidence line, only where exactly one symbol can be meant: same type first for bare calls, `this.`/`base.`, `Type.Member(` for a known type, receivers whose declared type is known (parameters, locals, fields, `var x = new T(...)`), `new T(` to T's constructor; ambiguous or unknown calls get no edge and are counted as unresolved, so packs say "incomplete" |
| F3 | Test discovery: `.cs` files in test projects or named `*Test(s).cs` are test files; test methods are those carrying a test attribute; `test_inventory` labels them `csharp` |
| F4 | `is_test_path` treats those files as test code, so packs list them under "Test files" |
| F5 | Every pack and MCP tool works on C# symbols without a language-specific code path |
| F6 | README language table: C# supported, with what it cannot do |

**Non-functional.**

| # | Requirement |
|---|---|
| N1 | Standard library only: no Roslyn, no .NET SDK, no tree-sitter; devkb must run where .NET is not installed |
| N2 | Precision first: a wrong edge is worse than a missing one; sampled `CALLS` precision ≥ 0.95 |
| N3 | No change to any Python or TypeScript graph: `make verify` identical, registry pack check 1.0 |
| N4 | MediatR builds in under 10 seconds |
| N5 | No new node type or verb (no ADR-gated schema change) |

**Out of scope.** VB.NET, F#; ASP.NET routes as `Endpoint` nodes (follow-up); Razor (`.cshtml`); LINQ query syntax
calls; overload resolution by argument types.

## 3. Architecture (architect)

**Decision.** A new module `devkb/csharp_symbols.py`, built like the C/C++ scanner (`cpp_symbols.py`, the same
standard-library design) and wired into `build_symbols.extract` with one call, `csharp_symbols.add_to_graph(g,
repo_root)`. No Roslyn: it would make devkb depend on the .NET SDK (N1) and on building the project, which fails on
many checkouts. This follows an existing precedent and adds no node type or verb, so it needs no ADR (N5); it is
recorded here as Proposed for the maintainer's review in the pull request.

**Two passes per file.**
1. `mask`: blank comments, every string form (regular, verbatim, interpolated with nested braces, raw), character
   literals and preprocessor lines (`#if`, `#region`, `#pragma`, ...), keeping every newline so line numbers hold.
2. `scan_file`: walk `{`, `}` and `;` with a scope stack. The text since the last `;`/`{`/`}` is the header of what a
   brace opens: a namespace, a type (name, generic arity dropped, base list), a member (method, constructor,
   property, operator, local function), or a block (`if`, lambda, initializer), whose calls belong to the enclosing
   member. A file-scoped namespace (`namespace A;`) sets the scope until the end of the file. An expression-bodied
   member (`... => expr;`) is a member whose body runs to the `;`.

**Call resolution (`_Index`).** Symbols by name, types by name (merging partial types across files), members by
(type, name), base lists for inheritance. A call names one symbol when: a bare `M(` matches exactly one member of
the enclosing type or its bases, or one local function; `this.M(`/`base.M(` likewise; `T.M(` where T is a known type;
`x.M(` where x's declared type T is known (parameter, local `T x`, `var x = new T(...)`, field or property of the
enclosing type); `new T(` to T's constructor or, without one, to T. Overloads in one type share one key (as in
Python), so a call to an overloaded name still resolves to that member. Anything else is declined and counted in
`unresolved_calls`.

**Tests.** `test_discovery`: `_CS_TEST` matches `.cs` files under a directory named like a test project
(`*.Tests/`, `*.Test/`, `*Tests/`, `test/`, `tests/`) or named `*Tests.cs`/`*Test.cs`; `tests_in_file` returns methods
preceded by a test attribute. `process_api.is_test_path` adds `_CS_TEST`. Test methods are also symbols, so their
calls into the code are `CALLS` edges and the existing "test files among the callers" logic works unchanged.

## 4. Story

#32: *As a developer whose repository is written in C#, I want devkb to build a graph of my C# code, so that my
coding agent gets the same one-call answers Python users get.* Acceptance criteria (copied from #32):

1. `pytest tests/test_csharp_symbols.py` passes on a fixture covering namespaces (block and file-scoped), classes,
   structs, interfaces, records, generics, overloads, extension methods, properties, constructors, local functions
   and xUnit/NUnit/MSTest tests.
2. `devkb build` on MediatR at `1fad4c7a` produces at least 500 `Symbol` nodes and at least 200 `CALLS` edges.
3. Given 40 `CALLS` edges sampled with a fixed seed from MediatR, when each is checked against the source, then at
   least 38 are correct; the sample and verdicts are committed.
4. `devkb pack refactor` on a MediatR method with test callers lists its caller files and at least one test file.
5. Python graphs unchanged: `make verify` identical; the registry pack check still 1.0.
6. (Added during the work, owner rule for every new language) the extractor is dogfooded on at least 3 real
   repositories pinned in `bench/languages.yaml` (MediatR, FluentValidation, Polly), with a precision sample from each
   (`csharp-precision-sample.md`) and a CI step that fails if their counts drop.

## 5. Readiness (ODSF G0)

| Check | State |
|---|---|
| R1 story traces to a specification | #32 → this document |
| R2 specification traces to a need | #25 (user feedback) |
| R3 ≥ 3 falsifiable acceptance criteria, at least one failing today | 5; criterion 2 fails today (0 symbols) |
| R4 scope boundary stated | §2 Out of scope; #32 Scope |
| R5 no schema change without an accepted ADR | none (N5) |
| Spec status | Proposed: the maintainer accepts it by merging the pull request |

## 6. Use of devkb during implementation

The packs and tool answers used while building this are kept in `docs/specs/csharp-devkb-use.md`: the file packs for
`build_symbols.py` and `test_discovery.py` (what depends on them, which tests to run), and refactor packs for
`list_test_files` and `is_test_path` (every caller that must keep working).
