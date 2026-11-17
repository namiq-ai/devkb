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
