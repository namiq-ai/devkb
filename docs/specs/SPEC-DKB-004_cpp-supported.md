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

**Baseline, restated by story 1** (`bench/cpp/truth_clang.py` + `bench/cpp/quality.py` + `bench/cpp/adjudicate.py`, libclang 18,
devkb 0.2.11, the pinned corpus of `devkb/bench/cpp_corpus.json`; the third C++ repository is tinyxml2, pinned there as
`adjudication_repos`). The truth now keeps recursive calls, excludes vendored paths (`vendored` in the corpus file:
cJSON `tests/unity`, fmt `test/gtest`, leveldb `third_party`) and lists the translation units it could not compile.
Numbers as `quality.py` reports them; the sample is `docs/specs/cpp-precision-sample.md`.

| | cJSON (C) | leveldb (C++) | fmt (C++, template-heavy) | tinyxml2 (C++) |
|---|---|---|---|---|
| Truth definitions / call edges (recursive among them) | 355 / 835 (8) | 2,024 / 3,898 (0) | 4,084 / 1,778 (3) | 421 / 750 (2) |
| of which only through a macro expansion | 2 (0.2%) | 525 (13%) | 491 (28%) | 4 (0.5%) |
| Translation units not compiled (listed, `not_measured`) | 0 | 4 of 77 | 0 of 48 | 0 of 3 |
| devkb edges linked / scored by the truth | 1,068 / 805 | 2,159 / 1,692 | 1,825 / 1,093 | 450 / 446 |
| of which not scored: vendored / not measured / unmapped end | 260 / 0 / 3 | 0 / 126 / 341 | 398 / 0 / 334 | 0 / 0 / 4 |
| Edge precision against the truth (as measured) | 1.000 | 0.967 | **0.381** | 0.814 |
| **Adjudicated precision** (100 edges, 95% interval) | **1.000** (0.963 to 1.000) | **1.000** (0.963 to 1.000) | **0.930** (0.863 to 0.966) | **0.990** (0.946 to 0.998) |
| Edge recall | **0.964** | **0.420** | **0.252** | **0.479** |
| Symbol recall (truth USRs / distinct names) | 1.000 / 1.000 | 0.616 / 0.621 | 0.311 / 0.345 | 0.765 / 0.976 |

*Before story 1* (truth without recursion, without exclusions; leveldb and fmt tests read without gtest):
cJSON 0.983 / 0.453, leveldb 0.897 / 0.545, fmt 0.425 / 0.208 (precision / recall).

**The measured precision is not the real precision, and the adjudicated sample says by how much.** On fmt the truth scores
0.381 and a hand check of 100 edges finds 0.930: of 76 sampled edges the truth called wrong or could not map, 69 are
right. The 7 errors are real: four calls to `copy` with three arguments sent to `format.h`'s two-argument string-view
overload instead of `core.h`'s iterator overloads, a member initialiser `begin(std::move(b))` read as a call to a free
`begin`, a gmock `EXPECT_CALL(alloc, allocate(size))` read as a call, and `::dup2` inside `test::dup2` read as a call to
itself. On leveldb all 15 hand-judged edges are right; on tinyxml2 15 of 16 (`node->~XMLNode()` linked to the
constructor). What the truth gets wrong is, as the first draft of this spec said, mostly calls it cannot see: inside
uninstantiated templates (`RoundUp<4>(p)`, `max_value<uint32_t>()`, `write_exponent<Char>`), behind annotation macros
(`locks_.Insert` after `LOCKS_EXCLUDED`), and in `TEST_F` bodies it reads as generated classes.

**What the first draft got wrong** (all three found while building the measurement):
- `truth_clang.py` dropped every recursive edge (`a != b`); cJSON's 16 "wrong" edges were all recursive calls. Kept now.
- cJSON's "1,013 edges only through a macro" were vendored Unity's assertion macros (`tests/unity`): 260 of devkb's
  1,068 edges and 730 of its symbols are Unity's. Excluded now, cJSON's recall is **0.964** and its macro-only edges are 2.
  The macro gap is leveldb's (521 missed) and fmt's (491), not cJSON's.
- 36 of leveldb's 77 translation units were flagged uncompilable, nearly all for a missing `gtest/gtest.h`: the
  `third_party/googletest` submodule is empty in a plain clone. With googletest at the pinned submodule commit (`a35bc76`, `-I .../googletest/include`) 4 remain:
  `util/env_windows.cc` (`windows.h`) and three `benchmarks/` files (`benchmark.h`, `sqlite3.h`, `kcpolydb.h`).
  Their devkb edges (126) are `not_measured`, neither right nor wrong. fmt compiles in full with `-I include -I test/gtest`.
- fmt's "1,385 vendored missed definitions" are excluded now; with 2,814 truth USRs still without a devkb symbol,
  fmt's own `include/` and `test/` still lose: 244 are overloads of `detail::map` and 171 of `uint128::uint128`
  (several truth USRs, one devkb symbol), the rest are test bodies the `TEST` macros turn into classes. Symbol recall
  by distinct name (0.345) is the fairer figure; story 5 decides fmt's target from it.
- `bench/cpp/split_wrong.py`, which this section cited, was not in the repository; the adjudicated sample replaces it.

**Findings that move later stories' targets.** Story 2's "cJSON edge recall ≥ 0.80 (from 0.453)" is met by the truth
fix alone (0.964); its macro work is measured on leveldb and fmt. N2's 0.70 for C++ is far off on this truth: leveldb
0.420, tinyxml2 0.479, fmt 0.252. N1 (adjudicated ≥ 0.95) holds on cJSON, leveldb and tinyxml2 and is not shown on fmt
(point 0.930, interval to 0.966); 4 of its 7 errors are one cause, the overload pick across files.

**What is really missing** (missed truth edges by callee kind, the F1 truth):

| | cJSON | leveldb | fmt | tinyxml2 |
|---|---|---|---|---|
| call produced by a macro expansion | 2 | 521 | 491 | 4 |
| constructor | 0 | 506 | 198 | 19 |
| method (class member) | 0 | 1,068 | 0 | 360 |
| free function, same file | 0 | 69 | 204 | 6 |
| free function, other file | 28 | 97 | 437 | 0 |

The scanner already records every `#define` with its body (`cpp_symbols.py:177`). The resolver knows the
repository's macro names and drops calls to them (`cpp_resolve.py:231`), so the macro gap in leveldb and fmt builds on
data devkb already holds.

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
| 2 | **Calls through repository macros** (F2) | cJSON edge recall ≥ 0.80 (0.964 on the F1 truth, §1: Unity's macros are vendored); leveldb macro-only misses (521) found by ≥ 80%; adjudicated `cpp-macro` precision ≥ 0.95 on cJSON and leveldb; fixtures: a repository macro calling `f` links its invokers to `f`, a system-header macro is not expanded, nesting stops at depth 4, `#if` variants are marked |
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
