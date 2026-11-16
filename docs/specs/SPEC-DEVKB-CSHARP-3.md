---
id: SPEC-DEVKB-CSHARP-3
title: "C# round 3: typed expressions — call results, lambdas, .NET's own types, argument types"
type: spec
status: proposed
created: 2026-11-16
follows: SPEC-DEVKB-CSHARP-2
---

# C# round 3: typed expressions

Third round of C# support. BMAD roles: brief (§1), requirements (§2), architecture (§3), story (§4), readiness (§5),
results (§6, filled after the benchmark on the published release). devkb on its own code: `csharp-3-devkb-use.md`.

## 1. Brief (analyst)

**The three gaps 0.2.5 states** (README, `csharp-precision-sample.md` Round 2):
1. calls on a call's result, `a.B().C()`: 5–30% of call sites to repository names;
2. .NET's own type hierarchies: an extension on `TextReader` is not found for a `StreamReader`, one on
   `LambdaExpression` not for an `Expression<T>`; and the reverse, a repository extension cannot be ruled out where
   the .NET type has its own method of that name;
3. overloads by argument *type*: candidates are ruled out by argument count only.

**A new measurement: what a refactor pack misses.** Rounds 1–2 measured precision. This round adds caller-file
recall (`bench/cs_recall.py`): for 60 methods per repository whose name is defined once and is not a common .NET
member name, the truth is the files whose masked code contains `Name(`; the graph's answer is the files of its CALLS
edges, which is what `devkb pack refactor` lists.

| 0.2.5 | MediatR | FluentValidation | Polly | Jellyfin | EF Core |
|---|---|---|---|---|---|
| caller-file recall | 0.593 | 0.357 | 0.806 | 0.814 | 0.419 |
| caller-file precision | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Precision is perfect; an agent that trusts a pack misses up to two of three caller files. Reading the misses shows a
fourth gap the brief did not name:

4. **lambda parameters are untyped.** `services.AddMediatR(cfg => cfg.RegisterServicesFromAssembly(...))`: `cfg` is
   a `MediatRServiceConfiguration`, known from `AddMediatR`'s `Action<MediatRServiceConfiguration>` parameter. Builder
   lambdas are everywhere in .NET (EF Core `b => b.Property(...)`, Polly, ASP.NET options).

And a fifth, small: 5. property chains `a.B.C()` type only `Ns.Type.M()`, not `local.Property.M()`.

A first finding on the truth itself: names like `StartsWith` and `WriteLineAsync` are both repository methods and
.NET methods; the grep counted calls to `string.StartsWith` as callers. The .NET member table this round adds (F2) is
also what keeps the benchmark honest.

## 2. Requirements (PM)

| # | Requirement |
|---|---|
| F1 | **Call results are typed.** Each method records its return type with generic arguments. A call on a call's result (`a.B().C()`, across lines), on `(await a.B()).C()`, on a local `var x = a.B();` / `var x = await a.B();`, and on a `foreach (var x in a.B())` element resolves through the return type: `Task<T>`/`ValueTask<T>` unwrap under `await`; a sequence's element is its first generic argument. A return type that is a generic parameter is unknown |
| F2 | **.NET types.** A table of common .NET types (`devkb/csharp_dotnet.py`): bases and interfaces, and instance method names. An outside receiver accepts an extension whose `this` type is one of its .NET ancestors; an outside receiver whose type has an instance method of that name binds to it, never to an extension |
| F3 | **Argument types rule candidates out.** Where an argument's type is certain (string, numeric, bool, char literal, `nameof`, interpolated string, lambda, `new T(...)`, a typed local, parameter or field), a candidate whose parameter at that position cannot accept it is ruled out: a lambda into a non-delegate type, a literal into an incompatible primitive, a repository type into an unrelated repository type, an outside type into a repository type. Unknown argument or parameter types rule nothing out; named arguments switch the check off for that call. As in round 2, a ruling-out never makes a choice by itself |
| F4 | **Lambda parameters are typed** from the delegate parameter of the resolved method they are passed to: `Action<T>`, `Func<T, ...>`, `Expression<Func<T, ...>>`; for an extension call the `this` argument is skipped. Only single-parameter and parenthesised lambdas whose position is known |
| F5 | **Property chains**: `x.P.Q.M()` types `x`, then each property or field in turn |
| N1 | Precision first: sampled precision of edges added by this round ≥ 19/20 per repository; caller-file precision stays ≥ 0.98 |
| N2 | Caller-file recall rises on every repository; no repository's edge count falls without each sampled removal being a 0.2.5 error |
| N3 | Standard library only, no new node type or verb, EF Core builds in under 3 minutes |

**Out of scope:** generic type inference (`Foo<T>(T x)` resolving T from arguments), overload resolution's
betterness rules (only ruling-out), `dynamic`, LINQ query syntax, per-overload nodes.

## 3. Architecture (architect)

- **Return types** (`_type_ref`): from the raw member header, the text before the name, modifiers removed: outer
  simple name and simple generic arguments (`Task<IList<Order>>` → `Task`, `[IList]`; nested arguments kept as
  their outer name). Stored as `ret` (outer) and `ret_args`.
- **Expression types inside `_calls_in`.** Calls are visited left to right; each resolved call records the position
  of its closing parenthesis and its callee. A call whose receiver text ends in `)` looks up the call that closed
  there, or a parenthesised `await` around one. `_result_type(callee, awaited)` gives the receiver type. After each
  call, if the statement reads `var x = [await] <this call>;` or `foreach (var x in <this call>)`, `x` is typed.
- **Lambda parameters**: when a resolved callee has a delegate parameter at the argument's position whose generic
  argument is a type, the lambda's parameter name gets that type for the span of the lambda body.
- **.NET table**: `_Index.extension` and `member` consult `csharp_dotnet.ancestors/members` for outside receivers.
- **Argument types**: `_args(body, raw, k)` returns per-argument masked/raw text; `_arg_type` gives a simple type or
  None; `_Index.accepts(sym, arg_types, explicit_this)` rules out per F3. `fits` keeps its arity role.
- **Measurement**: `bench/cs_recall.py` (new), `bench/cs_stats.py`, `bench/cs_diff_sample.py`, `bench/cs_sample.py`;
  the final benchmark runs on the release installed from PyPI.

## 4. Story

*As a developer changing a method in a large C# codebase, I want the refactor pack to list the files that call it
through builders, chained calls and lambdas, so that I do not have to search for the callers the graph missed.*

Acceptance criteria:
1. Fixture tests for F1–F5, each failing on 0.2.5: chained call across lines; `(await x.A()).B()`; `var x = a.B()`;
   `foreach (var x in a.Items())`; lambda parameter from `Action<T>` and `Expression<Func<T, U>>`; `StreamReader`
   receiver finds a `TextReader` extension; `list.IndexOf(x)` on a `List<T>` never goes to an `IndexOf` extension;
   a string literal rules out an `int` overload in another type; a lambda rules out a `CancellationToken` parameter.
2. Caller-file recall rises on all five repositories (`bench/cs_recall.py --n 150`); caller-file precision ≥ 0.98.
3. Edges added against 0.2.5: 20 sampled per repository, ≥ 19/20 correct each; removed edges sampled and explained.
4. A random sample of 20 edges per repository from the final graph: ≥ 19/20 correct each.
5. EF Core builds in under 3 minutes; `bench/languages.yaml` minimums raised to the new counts.
6. The benchmark (recall, precision, counts, build time) re-run on the release installed from PyPI gives the same
   numbers as the branch.

## 5. Readiness (ODSF G0)

| Check | State |
|---|---|
| R1 story traces to a specification | this document |
| R2 specification traces to a need | owner request (round 3 of C#); the gaps 0.2.5 states |
| R3 ≥ 3 falsifiable criteria, one failing today | 6; criterion 1 fails on 0.2.5 by construction, criterion 2 has a measured baseline |
| R4 scope boundary | §2 Out of scope |
| R5 no schema change | N3 |
