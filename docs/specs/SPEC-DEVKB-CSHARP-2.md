---
id: SPEC-DEVKB-CSHARP-2
title: "C# at scale: linear builds, and choosing a call's target by its arguments"
type: spec
status: proposed
created: 2026-11-16
follows: SPEC-DEVKB-CSHARP
---

# C# at scale

Second round of C# support (first: `SPEC-DEVKB-CSHARP`, shipped in 0.2.4). Written with the ODSF lifecycle's BMAD
roles: brief (§1), requirements (§2), architecture (§3), story (§4), readiness (§5). The packs devkb gave on its own
code while doing this are in `csharp-2-devkb-use.md`.

## 1. Brief (analyst)

**Why now.** 0.2.4 was checked on three mid-sized libraries. The owner asked for two big, well-known C# projects;
**Jellyfin** (media server, 2,253 files, 367k lines, `2953ed632c`) and **EF Core** (Microsoft's ORM, 5,874 files,
1.8M lines, `8859f78f10`) were added. They exposed what the small repositories hid.

**Findings on the two new repositories (0.2.4 extractor)**

| # | Finding | Evidence | Kind |
|---|---|---|---|
| A1 | EF Core **did not finish**: stopped after 15 min 55 s. Jellyfin took 36.6 s | `ps` elapsed time; `/usr/bin/time` | abnormality |
| A2 | Cause 1: local functions were looked up by scanning every symbol for every symbol (O(n²)); 8.5 of 34 s on Jellyfin | cProfile, `extract` self-time | bug |
| A3 | Cause 2: `body[:m.start()]` copied the whole body prefix for every call, quadratic in body size; one 1 MB generated method (`ManyTypesEntityType.cs`) ran over 300 s alone | timing one file | bug |
| A4 | After A2/A3, `mask` was 63 of 146 s on EF Core (113 M `startswith` calls, one character at a time) | cProfile | performance |
| A5 | The per-symbol `unresolved_calls` counts calls *to the name*, so a common name (`Add`, `Create`) shows thousands of unresolved calls on every method so named; summed over EF Core it is 3.2 M, meaningless as a rate | node properties | measurement |
| A6 | Precision sample, Jellyfin: 19/20. Wrong: `entity.Permissions.FirstOrDefault(p => ...)` sent to the repository's only extension `FirstOrDefault(this IReadOnlyList<T>)`, which takes no predicate: it is LINQ's. The "only extension so named" rule ignores the argument count | `csharp-samples/jellyfin.txt` #7 | precision bug |
| A7 | Precision sample, EF Core: 18/20. Wrong: (a) `property.ClrType.GetDefaultValue()` sent to `GetDefaultValue(this IReadOnlyProperty)`, because `GetDefaultValue([DynamicallyAccessedMembers(...)] this Type type)` was not seen as an extension: an attribute before `this` hid it; (b) `declaringEntityType.FindProperty(...)` on a `RuntimeEntityType : RuntimeTypeBase, IRuntimeEntityType` resolved through the interface, because bases were walked in alphabetical order, not declaration order (class base first) | `csharp-samples/efcore.txt` #2, #7 | precision bugs |

**Where call sites go** (`bench/cs_stats.py`; share of call sites whose name the repository defines; the
denominator also holds framework calls that merely share a name, so "resolved" is a lower bound):

| | MediatR | FluentValidation | Polly | Jellyfin | EF Core |
|---|---|---|---|---|---|
| resolved | 68% | 58% | 43% | 54% | 37% |
| chained, `a.B().C()` | 5.6% | 29.7% | 19.7% | 5.1% | 17.3% |
| receiver type unknown, several candidates | 9.1% | 1.5% | 11.9% | 15.3% | 30.5% |
| receiver typed, member not found there | 4.5% | 2.5% | 9.2% | 12.0% | 5.1% |
| several extension methods share the name | 0.0% | 0.1% | 8.9% | 3.8% | 2.0% |
| receiver unknown, one candidate | 12.2% | 8.0% | 3.5% | 8.2% | 4.6% |

**The two limitations named after 0.2.4.** (1) calls on a call's result (`a.B().C()`), and (2) choosing between
overloads by argument type. The owner asked for **the second** in this round. Overloads *within one type* already
share one key (as in Python), so for edges the argument types matter where **several symbols in different places**
share a name: extension methods (A6, A7a, Polly's 8.9%), a typed receiver whose member is not that type's (the call is
an extension or a framework method), and a bare call whose arity no overload accepts. (1) is the next round; its
size is measured above.

## 2. Requirements (PM)

| # | Requirement |
|---|---|
| F1 | A build is linear in symbols and in body size: EF Core finishes; no repository gets slower |
| F2 | Graphs are byte-identical to 0.2.4 after the performance changes alone (checked on the five repositories) |
| F3 | Each method records its arity range (required and maximum arguments; `params` means no maximum; an extension's `this` parameter excluded) and, for an extension, the type of its `this` parameter |
| F4 | A call's argument count is read from its text when it is certain (no `<` at the top level of the argument list); otherwise arity is not used for that call |
| F5 | A candidate whose arity range excludes the call's argument count is never chosen. This applies to every resolution path: bare, `this`/`base`, typed receiver, static `Type.M()`, extension |
| F6 | Extension calls: candidates are the extension methods so named that accept the argument count and whose `this` type is compatible with the receiver: the same type, a type it derives from or implements (in the repository), or a generic parameter. Known receiver of an outside type: only a `this` type with that name or a generic parameter. Unknown receiver: only when exactly one candidate fits the arity |
| F7 | An attribute in front of `this` does not hide an extension method |
| F8 | Bases are walked in declaration order (in C# the class base comes first), merged across partial declarations |
| F9 | Precision first: sampled precision on the final extractor ≥ 0.95 per repository, every error found investigated |
| N1 | Standard library only; no new node type, verb or property used by tools (no ADR) |
| N2 | `make verify` passes; Python graphs unchanged |

**Out of scope here:** chained calls (round 3), per-overload nodes (a refactor pack on a name covers all its
overloads, which a rename needs; a per-overload signature change stays a stated limit), argument *type* matching for
non-extension candidates in different types (precision risk without real type inference).

## 3. Architecture (architect)

- **F1/F2**: local functions indexed once by owner (`local_fns`); a bounded look-behind (`_LOOKBACK = 256`) for the
  text before a call; `mask` jumps between the characters that can start something (`_MASK_NEXT`). Checked by
  comparing `mask` output on all 9,309 `.cs` files and the graphs of five repositories against 0.2.4.
- **F3**: `_arity(params_text, ext)` → `(min, max)` from the raw parameter list (top-level commas, `=` defaults,
  `params`); stored on the symbol with `this_type`.
- **F4**: `_arg_count(body, open_paren)`: top-level commas up to the matching `)`; `None` when uncertain.
- **F5–F6**: `_Index` gets `fits(sym, n)` and `extension(name, n, rtype, near)`; `member()` filters each type's
  candidates by arity before declaring a hit and before walking bases.
- **F7**: attributes stripped from the parameter text before the `this` test.
- **F8**: `bases()` keeps declaration order.
- **Measurement**: `bench/cs_stats.py` (reasons per call site), `bench/cs_sample.py` (seeded samples), the
  `languages.yaml` minimums; neither writes to the graph.

## 4. Story

*As a developer on a large C# codebase, I want devkb's graph built in minutes, with calls sent only to a method that
can accept them, so that a pack's callers are right even where several methods share a name.*

Acceptance criteria:
1. EF Core at `8859f78f10` builds in under 5 minutes; MediatR, FluentValidation, Polly and Jellyfin no slower than 0.2.4.
2. With the performance changes alone, the five graphs equal 0.2.4's (sorted `nodes.jsonl`, `edges.jsonl`).
3. Fixture tests: an extension whose `this` follows an attribute is an extension; LINQ-shaped `x.FirstOrDefault(p => ...)` does not go to a parameterless extension; two extensions named alike on different `this` types each get their own callers; a class base wins over an interface; a call whose argument count no overload accepts gets no edge.
4. The three sampled errors (Jellyfin #7, EF Core #2, #7) no longer appear.
5. A seeded sample of 20 edges per repository, drawn from edges **added or changed** by this round, is ≥ 19/20 correct each, verdicts committed.
6. `bench/languages.yaml` lists the five repositories; CI checks the five (EF Core and Jellyfin only if within CI time; otherwise nightly).
7. `make verify` passes; registry pack check unchanged.

## 5. Readiness (ODSF G0)

| Check | State |
|---|---|
| R1 story traces to a specification | this document |
| R2 specification traces to a need | owner request (two big C# projects); #25/#32 |
| R3 ≥ 3 falsifiable criteria, one failing today | 7; criterion 1 fails today (EF Core does not finish) |
| R4 scope boundary | §2 Out of scope |
| R5 no schema change | N1 |

## 6. Results

| Criterion | Result |
|---|---|
| 1 EF Core < 5 min; others no slower | EF Core 120 s (0.2.4 did not finish); Jellyfin 36.6 → 11.9 s; MediatR, FluentValidation, Polly faster |
| 2 performance alone leaves graphs identical | identical on MediatR, FluentValidation, Polly, Jellyfin (EF Core has no 0.2.4 graph to compare); `mask` identical on 9,309 files |
| 3 fixture tests | `tests/test_csharp_symbols.py`, 19 tests; the four round-2 ones fail on 0.2.4 |
| 4 sampled errors gone | Jellyfin #7, EF Core #2, #7: all three fixed |
| 5 changed edges ≥ 19/20 | added: 20/20 on FluentValidation, Polly, Jellyfin, EF Core (1/1 MediatR); removed: 75/81 were 0.2.4 errors |
| 6 five repositories in `languages.yaml`, CI | done; CI builds all five |
| 7 `make verify`, tests | 291 passed; `make verify` passes |

Details and every abnormality found on the way: `csharp-precision-sample.md`, Round 2.
