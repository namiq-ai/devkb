---
id: SPEC-DEVKB-CSHARP-4
title: "C# round 4: generics carried through, overload betterness, dynamic, LINQ query syntax, third-party types"
type: spec
status: proposed
created: 2026-11-17
story: "#40"
follows: SPEC-DEVKB-CSHARP-3
---

# C# round 4

Fourth round of C# support (#40). BMAD roles: brief (§1), requirements (§2), architecture (§3), story (§4), readiness
(§5), results (§6, after the benchmark on the published release). Built on the latest `main` (`4ef4766`: 0.2.6 plus the
read tools, #39). **Dogfood**: every navigation question about devkb's own code during this round went to devkb first;
what it got wrong was recorded and, where in reach, fixed (`csharp-4-dogfood-log.md`).

## 1. Brief (analyst)

**Baseline on `main` at `4ef4766`, before any change** (the C# extractor is byte-identical to 0.2.6).

Caller-file recall and precision (`bench/cs_recall.py`, 150 methods per repository; precision 1.000 on all five):
MediatR 0.957, FluentValidation 0.888, Polly 0.915, Jellyfin 0.935, EF Core 0.775.

Call sites to repository names, by what happens to them (`bench/cs_stats.py`, `csharp-samples/round4-base-stats.txt`):

| | resolved | chained, receiver unknown | receiver unknown, several candidates | receiver typed, member not found | extension ambiguous |
|---|---|---|---|---|---|
| MediatR | 82% | 5.4% | 7.2% | 2.4% | 0.0% |
| FluentValidation | 83% | 11.6% | 0.7% | 0.4% | 0.0% |
| Polly | 52% | 16.7% | 11.0% | 6.9% | 6.8% |
| Jellyfin | 63% | 4.1% | 14.1% | 6.7% | 2.8% |
| EF Core | 47% | 14.7% | 23.8% | 7.2% | 1.5% |

**What the misses are.** Every caller file `cs_recall --show` reports missed on EF Core and FluentValidation (54) was
read at its call line and classified:

| Cause | Misses | Example | In #40's list |
|---|---|---|---|
| a .NET or third-party method of the same name (the benchmark's own truth noise) | ~11 | `Path.GetExtension`, `Expression.MakeMemberAccess`, `JsonElement.TryGetProperty` | third-party, partly |
| generic arguments not carried: a generic class's `T` from the receiver or a base list, `Lazy<T>.Value`, a method's `T` | ~6 | `_reporter.Value.ReportAsync()`; `RuleFor(x => x.CalculateSalary())` in an `AbstractValidator<Person>` | generic inference |
| a static call on a **generic type**, `Type<T>.M()` | 4 | `ValidationContext<T>.GetFromNonGenericContext(context)` (the value report's FluentValidation question) | no |
| explicit interface implementations matched as calls (truth noise) | 3 | `void IValidationRuleInternal<T>.AddDependentRules(...)` | no |
| a call after an unresolved call | 3 | `.TryWithExplicit(...)`, `.WhereAsync(...)` | no |
| element access, `x[i].M()` | 2 | `result.Errors[0].PropertyName.ShouldEqual(...)` | no |
| casts and patterns, `(T)x`, `x as T`, `x is T y` | 2–3 | `var rb = (RuleBuilder<T, P>)ruleBuilder; rb.AddComponent(c)` | no |
| `Expression<T>` receiving a `LambdaExpression` extension | 1 | `expression.IsParameterExpression()` | no |
| not explained by reading the line | ~6 | | |

So the issue's five items are real but not the largest; three gaps it did not name (static calls on generic types,
element access, casts and patterns) are as large, and the benchmark's truth needs two corrections of its own. All of
them are in scope.

## 2. Requirements (PM)

| # | Requirement |
|---|---|
| F1 | **Generic arguments carried through.** A generic type's parameters (in declaration order) are bound from the receiver's type arguments (`EntityTypeBuilder<Blog>` → `TEntity = Blog`) and from base lists (`class V : AbstractValidator<Person>` → `T = Person` inside V), and substituted into member return types, property types and delegate parameters. A generic method's parameters are bound from explicit type arguments (`M<Blog>(...)`) or, where an argument's type is known, from that argument (`M(x)` with `T x`). Outside generic types the table knows (`Lazy<T>.Value`, `Task<T>.Result`, `Nullable<T>.Value`, `KeyValuePair<K, V>`, `IEnumerator<T>.Current`) bind the same way |
| F2 | **Overload betterness.** When arity and certain argument types leave candidates under *different* keys, the better one is chosen by C#'s rules as far as they can be decided on certain types: identity over conversion, a more specific `this` or parameter type over a base, non-generic over generic, a repository type over `object`. If no candidate is strictly better on every certain argument, nothing is chosen (as before) |
| F3 | **`dynamic`**: a call on a receiver declared `dynamic` binds at run time: no edge, and not counted as an unresolved repository call |
| F4 | **LINQ query syntax**: `from x in src`, `join y in src2`, `let z = e` type their range variables (the source's element type; a declared type `from T x in` wins) for the rest of the query, so `where x.M()` resolves as method syntax would |
| F5 | **Third-party types**: data entries for types repositories call most and do not declare: ASP.NET Core MVC (`ControllerBase`, `Controller`), Microsoft.Extensions (`ILogger<T>`, `IOptions<T>`, `BackgroundService`, `IHostedService`), Moq (`Mock<T>`, its setup chain), each from the public API; bases, instance members and, for generics, which member returns which type argument |
| F6 | **Static calls on generic types**: `Type<A>.M(...)` is a static call on `Type` (with `A` bound for F1) |
| F7 | **Element access**: `x[i]` has the element type of `x` (arrays, lists, read-only lists, dictionaries' values) or the type of the type's indexer |
| F8 | **Casts and patterns**: `(T)x`, `x as T`, `x is T y`, `case T y`, `T y when ...` give their variable or expression type T (a declared type: it may rule out) |
| F9 | `Expression<TDelegate>` as a receiver is a `LambdaExpression` for extension choice (round 3 did this for arguments only) |
| B1 | **Benchmark truth**: `cs_recall` excludes explicit interface implementation declarations (`I...<T>.Name(`) and the static members of common .NET types (`Path`, `File`, `Expression`, `Math`, `Task`, ...) from its sampled names; both arms are scored on the same methods |
| N1 | Precision first: caller-file precision ≥ 0.98; sampled added edges ≥ 19/20 per repository; a random sample of the final graphs ≥ 19/20 per repository |
| N2 | Recall rises on EF Core and FluentValidation and falls on none |
| N3 | Standard library only; no new node type or verb; EF Core build within 20% of base |

**Out of scope:** full overload resolution (user-defined conversions beyond the implicit operators already seen,
optional-parameter tie-breaks, `params` expanded vs normal form), generic constraints solving beyond the first
constraint, `dynamic` member typing, source generators.

## 3. Architecture (architect)

- **Types as trees** (already `_pt`): `(name, (args...))`. A *binding* is `{T: type}`; `_subst(t, binding)` replaces
  parameter names inside a type tree.
- **Type parameters in order**: `tgparams_list` on types (declaration order), `gparams_list` on methods; the sets stay
  for membership tests.
- **Receiver bindings** (F1): `walk()` and the member lookup carry the receiver's type tree; when a member is found on
  type `q`, `bind(q, receiver)` maps q's parameters to the receiver's arguments, through base lists (a base written
  `AbstractValidator<Person>` contributes `T = Person`), and `_subst` is applied to its return/property type.
- **Method bindings** (F1): `_infer(callee, a_, explicit_args)`: explicit `<...>` from the call text (`_CALL` keeps
  it), else unification of parameter types with certain argument types (`T` ↔ a type; `G<T>` ↔ `G<A>` or a type whose
  ancestors include `G`). Applied to the result type and to delegate parameters before lambda typing.
- **Betterness** (F2): `_Index.better(cands, a_, rtype)`: per candidate a score vector over arguments whose type is
  certain (3 identity, 2 ancestor/conversion, 1 generic/object); a candidate wins only if it dominates every other.
- **Expressions** (F6–F8): a static generic-type call is recognised where the text before `.M(` is
  `Name<...>`; element access by `]` before the dot (`results` already keys call results by position; element
  access and casts add entries keyed by their closing bracket/parenthesis); pattern and cast declarations join
  `_locals_full` as declared types.
- **Query syntax** (F4): a pre-pass over each body finds `from`/`join`/`let` clauses and adds scoped entries (like
  lambda parameters) from the clause to the end of the query (the statement's `;`).
- **Tables** (F5, F7, B1): `csharp_dotnet.py` gains `GENERIC_MEMBERS` (member → type-argument index), static
  members of common types, and a third-party section; nothing inferred, each entry from the public API.

## 4. Story

*As a developer changing a method in a C# codebase built on generics, LINQ and third-party frameworks, I want devkb's
refactor pack to list the callers that reach it through those constructs, so that I do not search for them myself.*

Acceptance criteria (from #40, plus the measured items):
1. Baseline measured on `main` before code (§1).
2. A fixture test per item (F1–F9) that fails on `4ef4766` and passes after.
3. Caller-file recall rises on EF Core and FluentValidation, falls on none; precision ≥ 0.98 on all five (the base arm
   scored with the corrected truth of B1, on the same methods).
4. Every sampled added edge correct (20 per repository); every sampled removal a base error or explained.
5. Random sample of the final graphs ≥ 19/20 per repository.
6. Agent value report on the release: devkb-arm precision ≥ 0.85 and recall ≥ 0.96, against compiler truth.
7. EF Core build within 20% of base; `make verify`; standard library only.
8. README's C# row and SCOPE say what is handled now and what still is not.

## 5. Readiness (ODSF G0)

| Check | State |
|---|---|
| R1 story traces to a specification | #40 → this document |
| R2 specification traces to a need | #40; the stated limits of 0.2.6; the measured misses (§1) |
| R3 ≥ 3 falsifiable criteria, one failing today | 8; criteria 2 and 3 fail on the base |
| R4 scope boundary | §2 Out of scope |
| R5 no schema change | N3 |

## 6. Results

| Criterion | Result |
|---|---|
| 1 baseline before code | §1, measured on `4ef4766` |
| 2 a fixture test per item, failing on the base | `tests/test_csharp_symbols.py`: 8 round-4 test functions (F1–F9) fail on `4ef4766`, pass now; every regression the benchmark found has its own test (14 more) |
| 3 recall rises on EF Core and FluentValidation, falls on none; precision ≥ 0.98 | FluentValidation 0.841 → 0.870, Polly 0.851 → 0.866, MediatR, Jellyfin unchanged, **EF Core unchanged (0.933 → 0.933): not met**; precision 1.000 on all five. Owner's decision: release with this criterion stated unmet. On the corrected sample EF Core's base already reaches 0.933 |
| 4 sampled added edges correct, removals explained | 82/82 added edges correct (2 + 4 × 20); every sampled removal a base error or a move to the declaration the compiler binds (`csharp-4-precision.md`) |
| 5 random sample ≥ 19/20 | 100/100 (20 per repository) |
| 6 agent value report on the release: precision ≥ 0.85, recall ≥ 0.96 | on 0.2.7 installed from PyPI, on the fixed compiler truth: **precision 0.93 (met), recall 0.90 (not met)**; 0.2.6 on the same truth 0.94 / 0.91; median cost −53% against plain (0.2.6: −40%). First published as precision 0.82: the truth tool recorded calls only (not property reads) and merged two Polly classes; both fixed and the truth regenerated (`bench/exercises/csharp/DEVKB-VALUE-0.2.7.md`, `truth-corrections.md`). The recall shortfall is Polly: names credited through a lambda, and `Implementation` misses present since 0.2.6 |
| 7 EF Core build within 20%; verify; standard library | 164.7 s against 142 s (+16%); `make verify` passes; no dependency added |
| 8 README and SCOPE | README's C# row rewritten |

**Dogfood** (`csharp-4-dogfood-log.md`): seven limitations of devkb found by using it on its own code during the round;
five fixed with tests (D1 private classes typing receivers, D2 the Incomplete count, D3 recursive evidence lines, D4
`uses` and data files, D7 nested functions), two noted (D5 phrase search in `docs`, D6 the `uses` hint).
