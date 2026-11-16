# C# CALLS precision, checked by hand (#32)

Each sample is drawn with `python bench/cs_sample.py REPO GRAPH N` (seed 2032) from the graph `devkb build` made of
the repository at the commit pinned in `bench/languages.yaml`. For every edge the call line and the definition line
are printed; an edge is **correct** when the call on that line can only mean that definition (C# name lookup:
nested type, enclosing type and its bases, namespace, `using`). The raw samples are in `csharp-samples/`.

| Sample | Extractor state | Edges | Correct | Wrong, and what was fixed |
|---|---|---|---|---|
| MediatR 1 (`mediatr-1-before-fixes.txt`) | first version | 40 | **38** | #14 a declaration `Task Handle(...)` read as a call; #37 `new Ping()` resolved to a Ping in another namespace (a byte-order mark hid the file-scoped namespace). Both fixed: declarations are skipped, the BOM is masked, the nearest scope's type wins |
| MediatR 2 (`mediatr-2.txt`) | after those fixes | 40 | **40** | |
| MediatR 3 (`mediatr-3-final.txt`) | final: extension calls on external receivers, tuple return types | 40 | **40** | |
| FluentValidation (`fluentvalidation.txt`) | final | 20 | **20** | |
| Polly (`polly.txt`) | final | 20 | **20** targets | 6 edges (#14–17, #19, #20) on calls split over lines (`Policy` ⏎ `.Handle<T>()`) carried the line of the chain's start, not of the method name. Targets right; evidence now points at the name's line (test `test_a_chained_call_split_over_lines_carries_the_line_of_its_name`) |

**Final extractor: 120 of 120 sampled edges correct across three repositories** (acceptance criterion 3 asks for 38
of 40 on MediatR). Sample 1 is kept to show what the first version got wrong.

Two things found on real code and not in the fixture before: a tuple return type `(int A, string B) Name(...)` was
taken as the member's parameter list (a member named `static`), and an extension method called on a receiver of an
external type (`services.AddMediatR(...)` on `IServiceCollection`) got no edge. Both are fixed and in the fixture.

What the graph still does not see, by design (precision first): calls on an expression's result
(`a.B().C()`), on a `var` whose initialiser is not `new T(...)`, overloads told apart by argument types (overloads
share one key), and LINQ query syntax. These are counted as unresolved, so a pack says *incomplete* when they matter.

## Per-repository counts (`python -m devkb.bench.languages check csharp`)

| Repository | Commit | `.cs` files | C# symbols | CALLS | Test cases | Build |
|---|---|---|---|---|---|---|
| MediatR | `1fad4c7a35` | 160 | 1,560 | 666 | 246 | ~1 s |
| FluentValidation | `5903fa6586` | 219 | 2,180 | 3,282 | 842 | 2.0 s |
| Polly | `3bac1c877a` | 803 | 5,547 | 5,295 | 2,635 | 9.3 s |

Before this change all three produced no code nodes (MediatR: 4 nodes in total).

## Round 2 (SPEC-DEVKB-CSHARP-2): Jellyfin, EF Core, and choosing a target by its arguments

**0.2.4 on the two big repositories** (`jellyfin.txt`, `efcore.txt`, 20 edges each, seed 2032): Jellyfin **19/20**,
EF Core **18/20**. The three errors are A6 and A7 in the spec: a LINQ `FirstOrDefault(predicate)` sent to the
repository's only parameterless `FirstOrDefault` extension; `ClrType.GetDefaultValue()` sent to the wrong extension
because an attribute before `this` hid the right one; an interface searched before the class base.

**What the round changed, checked edge by edge.** `bench/cs_diff_sample.py REPO origin/main 20` lists every edge the
new resolver removed or added against 0.2.4 and draws 20 of each (`round2-diff-*.txt`). Each was checked against the
source:

| Repository | Edges 0.2.4 → now | Removed | of 20 sampled: 0.2.4 was wrong | Added | of 20 sampled: correct |
|---|---|---|---|---|---|
| MediatR | 666 → 666 | 1 | 1 of 1 (a 2-argument call sent to a 1-parameter override) | 1 | 1 of 1 |
| FluentValidation | 3,282 → 3,380 | 96 | 18 | 194 | **20** |
| Polly | 5,295 → 5,381 | 352 | 20 | 438 | **20** |
| Jellyfin | 12,584 → 12,621 | 356 | 18 | 393 | **20** |
| EF Core | 101,259 → 97,754 | 7,266 | 18 | 3,761 | **20** |

**Added edges: 81 of 81 sampled correct. Removed edges: 75 of 81 sampled were 0.2.4 errors; 6 were correct and are
now lost**, for two stated reasons: an outside type's hierarchy the repository cannot see (`Expression<T>` is a
`LambdaExpression`, `StreamReader` a `TextReader`: FluentValidation 2, EF Core 1), and a call on a receiver of unknown
type whose name some repository type also has as an instance method, declined as ambiguous (`User.GetDeviceId()`,
`context.Database.OpenConnectionAsync()`: Jellyfin 2, EF Core 1). On EF Core the edge count falls because 0.2.4 was
guessing: about 6,500 of the 7,266 removed edges were wrong (18/20 of the sample), against about 700 correct ones lost
and 3,761 correct ones added.

**Abnormalities the benchmark showed while the rule was being built, and what each changed** (all now in the tests):

| Seen | Cause | Change |
|---|---|---|
| MediatR lost 63 correct `services.AddMediatR(...)` edges | an outside receiver (`ServiceCollection`) required the exact `this` type; it implements `IServiceCollection` | outside receivers accept `T` and `IT` |
| Jellyfin gained 441 edges to two `Contains` extensions | the argument count narrowed several candidates to one, and "the one left" was taken: every `list.Contains(x)` | the argument count only rules candidates out, it never chooses |
| Jellyfin lost 62 `User.GetUserId()` | `User` is a property and also a class name: read as a static call | a failed static lookup may still be an extension call |
| Jellyfin lost `series.SetProviderId(...)` | the walk up the hierarchy stopped at 32 types; two classes are named `Series` | no cap; several same-named types: union of their hierarchies |
| Jellyfin lost static calls `PathExtensions.Attr(p, "x")` | an extension called statically passes `this` as an argument | arity counts `this` when no receiver is written |
| Jellyfin: `using var canvas = new SKCanvas(...)` untyped (also in 0.2.4) | the local pattern read `using` as a type | keywords are not types |
| Polly: 178 then 152 edges to a benchmark helper `ExecuteAsync(this object, ...)` | partial-class overloads made the member lookup ambiguous, then an `object` extension caught it; outside receivers (`restClient`) too | a member that fits, even ambiguously, beats any extension; `this object`/`this T` on an invisible receiver only if no repository type has an instance method of that name |
| FluentValidation: 279 correct `ShouldEqual` edges lost by the first version of that rule | blocking every `object` extension on invisible receivers | the instance-method test instead (properties and static methods do not count) |

**Final call-site picture** (`round2-call-sites-final.txt`, against `round2-call-sites-0.2.4.txt`): calls on a
call's result are unchanged (MediatR 5.6%, FluentValidation 29.7%, Polly 19.7%, Jellyfin 5.1%, EF Core 17.3%): that
is round 3. "Resolved" moves little (EF Core 37% → 34%) because the precision rules now decline guesses that used to
count as resolved.

**Build** (`devkb build`, whole graph): MediatR 1.2 s, FluentValidation 1.8 s, Polly 6.0 s, Jellyfin 11.9 s
(0.2.4: 36.6 s), EF Core 120 s and 1.0 GB peak memory (0.2.4: did not finish in 16 minutes).
