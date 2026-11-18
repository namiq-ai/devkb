---
id: SPEC-DKB-004
title: "C and C++ move from Partial to Supported: call edges an agent can trust, measured against the compiler"
type: specification
doc_type: prd
track: brownfield
status: proposed
created: 2026-11-17
updated: 2026-11-17
owner: PO
source: owner request 2026-11-17 ("we are at full support level?" — no; write the spec and file the tickets)
supersedes: []
superseded_by: null
extends: SPEC-DKB-002
tickets: ["#124 (epic)", "#117-#123 (stories 1-7)", "#114-#116 (defects found writing this spec)"]
---

# SPEC-DKB-004: C and C++ Supported

BMAD roles: brief (§1), requirements (§2), architecture (§3), stories (§4), readiness (§5), results (§6, after the
release that closes the stories). Baseline: `main` at `632f8d0` (0.2.11).

## 1. Brief (analyst)

The README marks C/C++ 🟡 Partial. C# reached ✅ Supported only after it was checked against its compiler on five
repositories (precision 0.93, recall 0.90) and entered the CI language check. The owner's language rule
(2026-11-16) asks for at least 3 real repositories, a sampled precision and a CI check. C/C++ has none of the three
at the Supported level: `bench/languages.yaml` holds only C#, and the compiler-truth numbers in
`docs/evaluations/CPP-FINAL-REPORT.md` predate SPEC-DKB-002 and the 0.2.8 audit fixes.

**Baseline, measured for this spec** (`bench/cpp/truth_clang.py` + `bench/cpp/quality.py`, libclang 18, the pinned
corpus of `devkb/bench/cpp_corpus.json`; numbers as `quality.py` reports them):

| | cJSON (C) | leveldb (C++) | fmt (C++, template-heavy) |
|---|---|---|---|
| Truth definitions / call edges | 968 / 2,032 | 1,465 / 2,971 | 4,286 / 3,035 |
| of which only through a macro expansion | 1,013 (50%) | 362 (12%) | 503 (17%) |
| devkb edges linked / scored | 1,068 / 936 | 2,159 / 1,802 | 1,825 / 1,388 |
| **Edge precision (as measured)** | 0.983 | 0.897 | **0.425** |
| **Edge recall** | **0.453** | **0.545** | **0.208** |
| Symbol recall | 0.995 | 0.921 | 0.437 |

**The measured precision is not the real precision.** Every wrong edge was split by `bench/cpp/split_wrong.py`
(sampled up to 400 per repository):

| | cJSON | leveldb | fmt |
|---|---|---|---|
| Wrong edges | 16 | 186 | 798 (400 sampled) |
| callee called in the caller's body, truth has no such call | 16 | 170 | 361 |
| truth has another target of that name from this caller (a target pick) | 0 | 14 | 39 |
| callee's name not called in the caller's body (devkb plainly wrong) | 0 | 2 | 0 |

The first row is mostly the truth's fault, and hand checks confirm it:
- `truth_clang.py:124` drops every recursive edge (`a != b`). All 16 of cJSON's "wrong" edges are recursive calls
  (`cJSON_Compare` → `cJSON_Compare`).
- Files that do not compile on the measuring platform contribute no truth. leveldb's `util/env_windows.cc` calls
  `handle_.get()` on a `ScopedHandle`; devkb's edge is right, but the truth has nothing for the file.
- Calls that libclang does not resolve are missing. That covers calls inside uninstantiated templates whose
  arguments depend on a template parameter, and calls to explicit specialisations. fmt's
  `decimal_point` → `decimal_point_impl<char>` (format.h:1364) and `to_decimal` →
  `cache_accessor<T>::compute_delta` (format-inl.h:1309) are real calls with no truth edge.
- Three of three sampled leveldb edges in that row were correct: `BloomTest::Add` → `Slice::ToString`,
  `DBTest` → `EnvWrapper::RemoveFile` (inherited), and `env_windows.cc` → `ScopedHandle::get`.

That row also contains real errors, wherever the true callee is outside the repository (the truth drops it) and
devkb linked a same-named repository function. Only an adjudicated sample separates the two (F1).

**fmt's symbol recall is mostly vendored code.** Of the 1,525 truth definitions with no devkb symbol, 1,385 are in
`test/gtest/` (gmock and gtest), which the truth reads and devkb barely does. About 140 are in fmt's own files.

**What is really missing** (missed truth edges by callee kind):

| | cJSON | leveldb | fmt |
|---|---|---|---|
| call produced by a macro expansion | 1,013 | 362 | 502 |
| constructor | 0 | 453 | 241 |
| method (class member) | 0 | 462 | 989 |
| free function, same file | 0 | 18 | 370 |
| free function, other file | 99 | 56 | 301 |

The scanner already records every `#define` with its body (`cpp_symbols.py:177`). The resolver knows the
repository's macro names and drops calls to them (`cpp_resolve.py:231`), so the largest gap in C builds on data
devkb already holds.

## 2. Requirements (PM)

| # | Requirement |
|---|---|
| F1 | **A measurement that can be trusted.** The compiler truth keeps recursive calls, lists the files it could not compile on the measuring platform (scored as "not measured", not as wrong), and excludes vendored code (`third_party`, `vendor`, and test frameworks copied into the tree such as `test/gtest`) from truth and score alike. Precision is reported as **adjudicated precision**: a seeded sample of at least 100 edges per repository, each wrong-by-truth edge judged by hand against the source, with a 95% interval. The sample is committed as `docs/specs/cpp-precision-sample.md`, as C# did |
| F2 | **Calls through repository macros.** A call to a function-like or object-like macro defined in the repository becomes `CALLS` edges from the enclosing function to the repository functions called in the macro's body, through nested repository macros up to depth 4, with source `cpp-macro` and a confidence below a direct call. Macros defined outside the repository are not expanded. A macro with several `#if` variants contributes the union of its variants and marks the edge `variant: true` |
| F3 | **Constructor calls.** `T x(args)`, `T x{args}`, `T(args)`, `new T(args)`, `std::make_unique<T>` / `std::make_shared<T>`, and base or member initialisers link to `T`'s constructor. With several constructors, the one whose arity fits is chosen; if several fit, the call stays unresolved and counted |
| F4 | **Receiver types an agent would read off the page.** A receiver's type is taken from: `auto x = T(…)`, `new T`, `make_unique<T>`/`make_shared<T>`; `std::unique_ptr<T>`, `std::shared_ptr<T>` and `T&`/`T*` (→ `T`); members declared in the class's header; `this->`; and a repository method's declared return type, for one level of chaining. A `TEST_F(Fixture, Name)` / `TEST_P` body is a method of a subclass of `Fixture`, so its unqualified calls resolve against `Fixture` and its bases (leveldb's `TEST_F(BloomTest, Small)` calls `Add`, today unlinked). A type not decided by these rules stays unknown: no guess |
| F5 | **Overloads by arity.** Several same-named targets in reach are narrowed by argument count; if more than one remains, the call stays unresolved, as today |
| F6 | **Definitions in the project's own files.** A function defined behind a project's attribute macros (`FMT_CONSTEXPR`, `FMT_FUNC`, `FMT_INLINE`, and the same shapes elsewhere) is a symbol. Target: symbol recall ≥ 0.95 on each repository's own (non-vendored) files |
| F7 | **A CI check.** `bench/languages.yaml` gains `c` and `cpp` entries, each with at least 3 pinned public repositories and minimum symbols, calls and tests (about 80% of the measured value), run by `python -m devkb.bench.languages check` |
| N1 | Adjudicated edge precision ≥ 0.95 on every scored repository, for every edge source, the new ones included |
| N2 | Edge recall against the F1 truth: ≥ 0.80 on the C repositories, ≥ 0.70 on the C++ repositories. Template-heavy code is reported separately, with fmt's own target set when story 1 has measured what the truth can see there |
| N3 | Build time: at most +10% on Zephyr against 0.2.11 (`bench/perf.py`, same run, alternating) |
| N4 | No new node type or edge verb (`CALLS` with new `source` values only), so no ADR. Packs stay honest: an unresolved call still makes a pack Incomplete |

**Promotion rule.** The README row becomes ✅ Supported when N1 and N2 hold on every repository in F7, and the CI
check is green on `main`. The remaining limits (no template instantiation, no general type inference, function
pointers and ops tables unresolved) stay in the row in one short clause, as they do in every pack.

## 3. Architecture (architect)

- **Measurement** (F1): `bench/cpp/truth_clang.py` keeps `a == b` edges, records the translation units that failed
  or produced fatal diagnostics, and takes a vendored-path list from the corpus file. `bench/cpp/quality.py` reads
  the same list and reports `not_measured`. A new `bench/cpp/adjudicate.py` draws the seeded sample, shows each
  edge with the caller's body, and records verdicts in a JSONL file that the precision report reads.
  `bench/cpp/split_wrong.py` (committed with this spec) does the automatic first split.
- **Macros** (F2): `cpp_symbols.py` already records `(name, body, line)` per `#define`. A repository macro table
  maps each macro to the calls in its body, closed over nested macros, once per build. `cpp_resolve.py`, which
  today drops calls to repository macros (line 231), resolves the body's calls as if they were written at the
  invocation, from the invoking function's scope. `cpp_graph.py` emits them with source `cpp-macro`.
- **Constructors and receivers** (F3, F4, F5): `cpp_resolve.py`, which already holds `cpp-typed-receiver` and
  `cpp-qualified`. Local declarations get a small per-function type table; members come from the class records the
  scanner already keeps. Arity counting uses the masked argument text the scanner already produces.
- **Definitions** (F6): the attribute-macro list in `cpp_symbols.py`, extended from what story 1's
  missed-definition sample shows. It is a list, not a parser change.
- **CI** (F7): `bench/languages.yaml`, the `devkb.bench.languages` source names (`ast-c`, `ast-cpp` or the
  existing ones), and the nightly bench job.
- No dependency on libclang or `compile_commands.json` in the build. devkb reads files and runs `git`, never a
  compiler front end, and the graph must build where no build system is configured. libclang stays a
  measurement tool.

## 4. Stories

Each story is one ticket, filed before the work. Every story keeps `pytest` green and has fixture tests in
`tests/`.

| # | Story | Done when |
|---|---|---|
| 1 | **Trustworthy C/C++ measurement** (F1) | Truth keeps recursive calls; uncompilable files and vendored code are excluded and listed; `adjudicate.py` and `cpp-precision-sample.md` give adjudicated precision with a 95% interval on cJSON, leveldb, fmt and the third C++ repository; the baseline table above is re-stated on 0.2.11 with those numbers |
| 2 | **Calls through repository macros** (F2) | cJSON edge recall ≥ 0.80 (from 0.453); adjudicated `cpp-macro` precision ≥ 0.95 on cJSON and leveldb; fixtures: a repository macro calling `f` links its invokers to `f`, a system-header macro is not expanded, nesting stops at depth 4, `#if` variants are marked |
| 3 | **Constructor calls** (F3) | ≥ 80% of leveldb's 453 missed constructor edges found; adjudicated `cpp-constructor` precision ≥ 0.95; fixtures for each form in F3 and for an ambiguous arity (left unresolved) |
| 4 | **Receiver types and overloads by arity** (F4, F5) | leveldb edge recall ≥ 0.80; method misses on leveldb ≤ 100 (from 462); adjudicated precision of `cpp-typed-receiver` ≥ 0.95; fixtures for each rule in F4 and for an undecidable receiver (no edge) |
| 5 | **Definitions behind attribute macros** (F6) | symbol recall ≥ 0.95 on fmt's own files (vendored excluded) and on every F7 repository |
| 6 | **C and C++ in the CI language check** (F7) | `bench/languages.yaml` `c` and `cpp` with ≥ 3 pinned repositories each, minimums at about 80% of measured; the check runs in the bench workflow and passes on `main` |
| 7 | **README: C, C++ ✅ Supported** (promotion rule) | Only after stories 1–6 meet N1–N3: the row is promoted, `tests/test_devkb_cpp_limits_dkb007.py` asserts the promotion rule instead of "Partial", and §8 of this spec records the final numbers |

Order: 1 first, because every later target is measured with it. Then 2 (the largest gap), 3 and 4 together (same
resolver code), 5 and 6, and 7 last.

## 5. Readiness (G0)

| Check | State |
|---|---|
| Traces to a need | owner request 2026-11-17; README row 🟡 Partial; language rule (3 repositories, sampled precision, CI) |
| Falsifiable criteria | every story has a numeric target or a named fixture |
| Scope boundary | N4; §3 last point (no libclang in the build); template instantiation and function pointers out |
| Schema change governed | none needed (N4) |
| Evaluation designed before build | story 1 lands first; §1 is the baseline |
| Open risk | (1) N2's C++ target may be out of reach for template-heavy code; story 1 decides fmt's target from what is measurable, and the promotion rule names the repositories. (2) F2 can add many edges in macro-heavy C (Zephyr); N3 bounds the build cost and N1 the precision |

## 6. Evaluation: every story built with and without the guardrail

Each story is implemented by headless agents (Sonnet, the model of every earlier arm) on a fresh checkout of `main`
holding only the story's ticket, in two arms, 2 runs each:

| Arm | Setup |
|---|---|
| `devkb` | `devkb init --toolset lean-pack` (AGENTS.md instructions, MCP server, graph built at setup); guardrail off (`DEVKB_GUARDRAIL=0`) |
| `devkb + guardrail` | the same, with the pre-search guardrail on: every Grep, or grep/rg/git grep search, in a repository devkb serves adds a reminder to ask devkb first (`~/.claude/hooks/devkb-guardrail.py`, logged per firing) |

Per story, one table in the style of `docs/evaluations/CPP-FINAL-REPORT.md`: runs, wall time, turns, model calls,
grep calls, file loads, devkb calls, guardrail firings, tokens (context / output), cost. It also gives the story's
acceptance result: the numeric target from §4, measured by `quality.py` and the adjudicated sample, and the test
suite. The best passing run is reviewed line by line before it is merged. The question each table answers: does
the guardrail turn "devkb offered" into "devkb used", and does use change cost or outcome? (Bug-fix benchmarks to
0.2.11: devkb used in 8 of 84 runs where it was offered.)

## 7. How devkb was used to write this specification

The first draft was written with grep and sed. The owner asked whether devkb had been used, and every code question
in §1 and §3 was then put to devkb 0.2.11 and checked against the source (`docs/specs/cpp-supported-dogfood.jsonl`).

**9 queries: 5 right, 1 honestly incomplete, 1 misleading, 1 wrong, 1 with no tool for the question.**
devkb confirmed both facts §3 builds on, and named the enclosing functions grep did not (`mask_source`, `resolve`).
It found three defects of its own, now ticketed:
- `uses` labels top-level C++ declarations with a function that ended earlier ("in count_digits"), and lists them
  ahead of the real call sites, which it omits.
- `uses` merges two same-named definitions into one span (`compute_delta` "L339-1116").
- A `TEST_F` body's calls to its fixture's methods are not linked. The pack for leveldb's `BloomTest::Add` says
  nothing reaches it, and its search hint leaves out `util/bloom_test.cc`, the one file that calls it. That is
  added to F4.

## 8. Results

To be written after the release that closes stories 1–7.
