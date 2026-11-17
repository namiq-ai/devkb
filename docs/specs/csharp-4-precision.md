# C# round 4 (#40): what the benchmark showed, checked by hand

Measured against the base `4ef4766` (0.2.6's C# extractor), both arms on the same methods and the same pinned
repositories (`bench/languages.yaml`). Raw samples: `csharp-samples/round4-*`.

## Caller-file recall and precision (`bench/cs_recall.py REPO --ref 4ef4766`)

| | MediatR | FluentValidation | Polly | Jellyfin | EF Core |
|---|---|---|---|---|---|
| recall, base `4ef4766` | 0.974 | 0.841 | 0.851 | 0.857 | 0.933 |
| **recall, round 4** | 0.974 | **0.870** | **0.866** | 0.857 | 0.933 |
| precision, both | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

(`round4-recall.jsonl`; 150 methods per repository, the same for both arms.) EF Core does not rise: on the corrected
sample its base already finds 0.933 of the caller files. The misses listed before the last fixes
(`round4-base-misses.txt` for the base) were a .NET-name collision (`Encoding.UTF8.GetByteCount`, now in the table), a
nested class matched by name, lambdas and chains typed only through outside methods, and calls the last fixes reached
(`WithMinBatchSize`, `ArrayConstantExpression e =>`, `var x = a.B().C;`); the final code was not re-listed.

The truth itself was corrected first (B1): names that are static members of common .NET types (`Path.GetExtension`,
`Expression.Call`, `Encoding.UTF8.GetByteCount`, ...) and explicit interface implementation declarations
(`void IFoo<T>.Name(...)`) no longer count. That changed which 150 methods are sampled, so the base numbers here are
not comparable with 0.2.6's published ones (EF Core's base moved from 0.775 to 0.933 on the corrected sample).

## Edges against the base (`bench/cs_diff_sample.py REPO 4ef4766 20`)

| | MediatR | FluentValidation | Polly | Jellyfin | EF Core |
|---|---|---|---|---|---|
| edges, base → round 4 | 774 → 776 | 4,538 → 4,629 | 6,372 → 6,839 | 13,447 → 13,555 | 134,421 → 138,317 |
| removed | 0 | 2 | 0 | 5 | 30 |
| added | 2 | 93 | 467 | 113 | 3,926 |
| added, sampled and correct | 2/2 | 20/20 | 20/20 | 20/20 | 20/20 |

Every sampled removal was a base error (a .NET call: `string.Split`, `Array.IndexOf`, `File.ReadAllLines`,
`Enumerable.Empty`, `Regex.Matches`, `visitor.Visit(x)`; `Array.CopyTo` on an array) or an edge that moved to the
declaration the compiler binds (an interface-typed property's interface; a base type's method where the variable is
declared as the base).

**Random sample of the final graphs** (seed 2032, 20 per repository, `round4-random-*.txt`): MediatR 20/20,
FluentValidation 20/20, Polly 20/20, Jellyfin 20/20, EF Core 20/20 (checked: the `EventDefinition<T1, T2>` and
`ValueConverter<TModel, TProvider>` edges land on the generic class of the right arity).

**Build** (`devkb build`, whole graph): EF Core 164.7 s, 1.18 GB peak (0.2.6 measured 142 s in round 3 on the same machine: +16%).

## Found by the benchmark while building the round, each fixed and tested

| Seen | Cause | Change |
|---|---|---|
| Polly lost 283 edges (`ResilienceContextPool.Shared.Get(...)`) | the new type view read the first partial declaration only; `Shared` is declared in the other file | partial declarations merged (fields, bases, type parameters) |
| Polly lost `Policy.HandleResult(x).Or<T>()` | the generic overload bound `TResult`, its non-generic sibling could not: two result types, so none | overloads agreeing on the outer type keep it, most-bound arguments |
| EF Core: `TablesMappedToProperty1.FormatTables()` lost | EF Core declares its own `class List` (a test type), which shadowed `List<(string, string?)>` | a repository type shadows a .NET name only with the same generic arity |
| EF Core: `ToHexString(value1)` ruled out | `var value1 = (byte[])value;` read as a `byte` (the cast pattern dropped `[]`) | array casts kept |
| EF Core: `queue.Enqueue([failure])` bound to .NET's `Enqueue` | a collection expression cannot be the single `T` .NET's method takes; C# picks the repository extension on `IEnumerable<T>` | with a collection-expression argument the .NET member name does not decide |
| FluentValidation and Polly lost calls on `IRule<T, TProperty>` / `Provider<TResult, TSerialized>` | the arity check read the merged view, which keeps one parameter list for `Foo<T>` and `Foo<T, U>` | arity checked per declaration |
| EF Core: `WithOption(e => (TExtension)e.WithMinBatchSize(...))` missed | a lambda parameter typed by a class type parameter was not replaced by its constraint | constraints apply to lambda-scoped types |
| EF Core: `ArrayConstantExpression e => VisitArrayConstant(e)` | switch-expression arms did not declare their variable | `Type name =>` arms declare it |
| EF Core: `var complexType = a.B().Single().ComplexType;` untyped | `var` from a call chain ending in a property | the trailing property chain is walked |
| `where o.IsLate()` (query syntax) not even seen as a call | `where x.M(` read like a declaration `T Name(` | query keywords may precede a call |

## Stated limits after this round

Generic type inference beyond explicit arguments and direct unification (no constraint solving, no inference through
lambdas' return types); overload betterness only where certain argument types decide it; member names of .NET and
third-party types without signatures (a collection-expression argument is the only signature-shaped exception);
`dynamic` calls are not edges by design.

## 0.2.8: the audit's C# fixes (2026-11-18)

Eleven C# fixes from the 0.2.5 → 0.2.8 audit (`docs/analysis/devkb-for-auditing.md`): a verbatim string `@""""` hiding
the rest of the file (#57), sibling local functions (#58), identifiers starting with a non-ASCII letter (#59), two
quadratic paths (#60, #61), attributes holding braces hiding the next member (#78), explicit interface implementations
dropped with their calls (#79), `#if/#else` branches with unbalanced braces (#80), a finalizer read as the constructor
(#81), overloads sharing local functions (#82), UTF-16 files (#83). Measured on the same pinned repositories, `main`
(`4369145`) → 0.2.8, each changed edge sampled against the source:

| | MediatR | FluentValidation | Polly | Jellyfin | EF Core |
|---|---|---|---|---|---|
| edges | 776 → 777 | 4,629 → 4,677 | 6,839 → 6,851 | 13,555 → 13,571 | 138,317 → 139,690 |
| removed | 0 | 0 | 1 (wrong: `new Sentinel()` → its finalizer) | 0 | 11 (9 wrong edges; 2 real calls lost, #94) |
| added, sampled and correct | 1/1 | 11/11 | 13/13 | 11/11 | 30/30 |
| tests | 246 → 246 | 842 → 843 | 2,647 → 2,647 | 1,544 → 1,550 | 20,252 → 20,267 |

EF Core's additions are mostly explicit interface implementations (1,210), test methods behind brace-holding attributes
(41) and local functions (130); 32 false members from collection initialisers read as declarations are gone. The two
lost calls sit in a constructor's `: base(...)` initializer, which the extractor never reads; they were found only
through an offset bug that #79's work fixed (#94). EF Core build: 176.7 s and 177.0 s on `main`, 165.6–168.8 s on 0.2.8.

**About B1 (round 4):** round 4 removed explicit interface implementations from the benchmark truth as "truth noise";
the audit then found the extractor dropped them entirely (#79). Excluding a class of cases from the oracle hid the
product's gap in that class.
