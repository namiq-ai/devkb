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
