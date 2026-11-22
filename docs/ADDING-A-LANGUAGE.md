# Adding a language to devkb, from nothing to ✅ Supported

A guide written from what it took to bring C# and C/C++ (and what TypeScript's plan, SPEC-DKB-008, copied from them) to the level the README calls
Supported. Each phase has an exit test; do not start the next phase before the exit test holds. Where this says "measured", the number is in
`docs/specs/` or `docs/analysis/`; where it says "proposed", it has not been tried.

The shape of the work is always the same: **build the ruler first, then make the reader exact, then add calls, then tests, then say honestly what is
still missing, then put it in CI, and only then promote the README row.** C# and C/C++ were each done in rounds because the ruler came late.

## Principles (each one cost a round to learn)

1. **Precision before recall.** A wrong edge sends an agent to the wrong file and it trusts the pack. A missing edge is made visible by the pack's
   Incomplete line. Link only where exactly one target can be meant; otherwise leave the call unresolved **and counted**.
2. **The ruler comes first.** Without a truth from the language's own compiler, every number is a guess. C/C++ had no trusted measurement until story 1.
3. **Standard library only in the product.** No Roslyn, libclang, tree-sitter or compiler front end in `devkb build`: it must run where nothing is installed
   (SPEC-DEVKB-CSHARP N1; ADR-DEVKB-008 for C/C++). Compilers belong to the measurement tools under `bench/`.
4. **Say what the reader cannot see, in one place, and prove each claim.** One text (`CXX_LIMITS_TEXT`), read by the packs and by the README test, and one
   test per limit that demonstrates it. A limit you cannot demonstrate is removed, not kept (#311: "definitions behind attribute macros" was dropped after
   every shape extracted).
5. **Never mark Supported early.** The README row stays 🟡 Partial until the promotion rule holds on every pinned repository and the CI check is green.
6. **Every number names its truth and its blind spots.** A truth that cannot compile 25 of 48 translation units is a truth about the other 23.

## Phase 0: the brief and the requirements (a SPEC, before any code)

Write `docs/specs/SPEC-DKB-0NN_<lang>-supported.md` from SPEC-DKB-004 or SPEC-DKB-008 (brief, requirements F and N, architecture, stories, readiness,
evaluation, results). Fill in:

- **Language facts that shape the design** (a table: fact, consequence). C#: namespaces, partial types, expression-bodied members, verbatim and raw strings,
  attributes as test markers. C/C++: the preprocessor, headers that are both C and C++, overloads, templates.
- **F requirements**: one measurable item each: definitions and spans, calls, receivers or types, tests, read tools, the CI check.
- **N requirements** (the promotion rule; copy the numbers, change them only with a reason in the SPEC):

  | | |
  |---|---|
  | N1 | adjudicated edge precision ≥ 0.95 on every scored repository and every edge source |
  | N2 | edge recall against the truth ≥ 0.80 (0.70 for C++ where templates dominate; template-heavy code reported apart) |
  | N3 | symbol recall ≥ 0.95 and span accuracy ≥ 0.95 on each repository's own files, vendored code excluded |
  | N4 | build time at most +10% on the largest repository against the last release, same run, alternating |
  | N5 | no new node type or edge verb (`CALLS` with new `source` values), so no ADR is needed |

- **Three to five pinned public repositories** of different shapes (a library, a mid-size application, one large). Pin the commit.
- **The stories, in this order**: 1 measurement, 2 definitions and spans, 3 calls, 4 receivers and overloads, 5 tests, 6 read tools, 7 CI check, 8 README.

Exit: the SPEC is merged and its stories are filed as tickets with a falsifiable *Done when* (the repository's ticket standard).

## Phase 1: the ruler (story 1)

Build `bench/<lang>/truth_<tool>.py` that asks the language's own compiler for: every function definition (file, start, end, qualified name), every call
with the definition it resolves to, and the files it could not compile.

| language | truth used | note |
|---|---|---|
| C# | Roslyn (`bench/cs_truth_from_roslyn.py`) | five repositories, caller-file recall and sampled precision |
| C, C++ | libclang (`bench/cpp/truth_clang.py`; `pip install libclang`, gcc's include dir for builtin headers) | records `not_compiled` and `vendored`; keeps recursive calls |
| TypeScript, JavaScript | `tsc` (`truth_tsc.mjs`, planned in SPEC-DKB-008) | |

Rules for the truth:

- **List what it could not measure** (uncompilable files, vendored directories) and exclude them from both sides. Generated headers (a CMake-written
  `port_config.h`) and absent test frameworks are the usual cause: supply the defines the build would have, or accept "not measured".
- **Score with a script that explains its misses** (`bench/cpp/quality.py`, then `split_wrong.py`): wrong edges split into target picks (the truth
  names another overload), truth gaps (template bodies the compiler cannot resolve) and real errors. Report all three, never one number.
- **Fix the metric before the product.** Metric artifacts we hit: template ids (`basic_appender<T>` against `basic_appender`), `operator<<` truncated by a
  `<` strip, lambdas counted as definitions, a graph that keeps one node per overload set against a truth that has one per overload.
- **Adjudicate by hand a sample** (20 to 40 edges per source, written to `docs/specs/<lang>-precision-sample.md`) for N1. The truth is not the verdict.

Exit: `quality.py`-style output on all pinned repositories, committed with the baseline numbers, before any extractor change.

## Phase 2: definitions and spans (story 2)

Write `devkb/<lang>_symbols.py` (or `<lang>_symbols.py` plus `<lang>_graph.py` and `<lang>_resolve.py` when the language needs a global resolver, as C/C++).

1. **Mask first**: comments, string and character literals (every form: verbatim, interpolated, raw, template), preprocessor or attribute lines. Keep
   offsets and newlines so line numbers stay exact. A brace inside a string breaking the scope stack was the first bug in every language.
2. **Track scope** (namespace, class, function) with a stack, not regexes over the whole file.
3. **Emit one symbol per definition** with exact `line_start` and `line_end`.
4. **Skip generated and vendored paths** (`*.g.cs`, `obj/`, `third_party/`), and record the rule in one place.
5. **Look for files with zero symbols and many lines.** This one check found the biggest C/C++ defect: `FMT_BEGIN_NAMESPACE namespace detail {` made the
   scanner read one unknown head and lose the whole file (fmt symbol recall 0.787 to 0.953). Sort files by lines ÷ (symbols + 1) and read the top ten.
6. **Fixtures for every shape** (one test per masked form, per symbol kind, per head shape). Fixture code is synthetic.

Exit: N3 on every pinned repository, measured with the Phase 1 script.

## Phase 3: calls (story 3)

- **Link only a unique target.** Order: same class or file, then qualified name, then imports or includes, then globally unique. Two or more candidates
  after narrowing: no edge, and the call is added to the symbol's unresolved count so the pack says Incomplete.
- **Every edge has an evidence line** (`path:line: caller calls callee`) and a `source` name (`cpp-same-class`, `cpp-constructor`, ...).
- **Name collisions with the standard library** make false edges (`Encoding.UTF8.GetByteCount` in C#). Keep a table of well-known names that are never
  repository calls.
- **Visibility is a resolver input, not a detail.** In C/C++, a macro applies where its header is included and stops at `#undef` (#290), and a class
  defined in several platform headers is the one the caller includes (#244; this single rule moved leveldb's edge recall from 0.751 to 0.798 and its missed method edges from 177 to 88). Expect the
  analogue in every language: Java package and import visibility, Rust `mod`/`use` paths and `cfg`, C# `using` and partial types.
- **Overloads.** The graph keeps one node per name, so an edge to an overloaded method is "wrong" against a per-overload truth. Decide this once, state it,
  narrow by argument count, and have the pack list which caller reaches which overload (#291).
- **Do not guess types.** `auto x = f(); x.g()` is a documented limit until return types are tracked. A copy (`T x(other)` with `other` of type `T`) is not
  a call to a one-argument constructor.

Exit: N1 and N2 on the pinned repositories, with the three-way split of wrong edges reported.

## Phase 4: tests (story 5)

Test discovery is per framework: C# `[Fact]`/`[Test]`/`[TestMethod]`, C/C++ gtest `TEST`/`TEST_F`, JS Jest and Vitest. Wire it in:
`devkb/test_discovery.py` (what is a test file and which cases it holds), `devkb/extractors/test_inventory.py` (the framework label),
`is_test_path`. A fixture per framework, and a pack on each pinned repository must list tests under "Test files". Exit: the QB1-style check (tests
that cover a changed function, `bench/quality/qb1_tests.py`) is not worse than an import search.

## Phase 5: wire it into devkb (the touch-points)

| where | what |
|---|---|
| `devkb/build_symbols.py` | list the language's tracked files; call its `add_to_graph(g, repo_root)` once |
| `devkb/process_api.py` (`_EXT_LANG`), `devkb/misses.py` (extension to language), `devkb/read_tools.py` (language name, import-line pattern for `outline`) | so read tools and the miss log know the extension |
| `scripts/devkb_guardrail.py` (code-extension list, `--include` glob table) | so a search of the language is answered or hinted from the graph |
| `devkb/test_discovery.py`, `devkb/extractors/test_inventory.py` | Phase 4 |
| `devkb/packs.py` | usually nothing: packs are language-blind. If a pack needs a note, add it to the language's limits text, not to `packs.py` |
| `README.md` language table, `tests/test_devkb_<lang>_limits_*.py` | Phase 6 |
| `bench/languages.yaml` | Phase 7 |

Rule: no language-specific code path in a pack or an MCP tool (SPEC-DEVKB-CSHARP F5).

## Phase 6: honest limits (the README row stays 🟡 Partial)

One constant holds the text (`CXX_LIMITS_TEXT`, `C_LIMITS_TEXT`), packs print it after the Coverage line, and the README row repeats the same phrases. The
limits test checks that the two agree and has one `test_limit_*` per limit that **demonstrates** it on a fixture. Update the text whenever a ticket
changes what is true; the test fails if you forget.

## Phase 7: the CI language check (story 7)

Add `bench/languages.yaml` entries: `source`, and per repository `id`, `url`, `commit` (40 characters), and `min_symbols`, `min_calls`, `min_tests` at **about 80%
of the value measured now**. `python -m devkb.bench.languages check <lang>` clones at the pin, builds, and fails below a minimum; CI runs it on every push.
Keep CI-sized repositories here (seconds, not minutes); a very large one (Zephyr: 136k symbols, 3.6 minutes) belongs to the corpus performance check
(`devkb/bench/cpp_corpus.json` budgets). A test pins the registry rule (3 repositories, 40-character pins).

## Phase 8: performance (N4)

- **Time the largest repository against the last release, alternating** old, new, old, new, on an idle machine; other work running at the same time adds noise to a timing that is judged against a 10% bar.
- **Profile both and compare function by function** (`cProfile`, same repository). Three of our own additions made up most of the regression on Zephyr: a
  breadth-first search per macro name, a regex alternation over thousands of class names, and two AST walks per Python function.
- **Test complexity by counting calls, not seconds** (`test_build_same_name_linear_289.py`): wall-clock tests flake under load (#377).
- A search for `X|Y|Z` over thousands of names is quadratic in Python's `re`; scan identifiers and look them up in a set.

## Phase 9: promotion

Only when N1 to N4 hold on every pinned repository and the CI check is green on `main`: the README row becomes ✅ Supported with the remaining limits in one
clause, the limits test asserts the promotion rule instead of "Partial", and the SPEC's results section records the final numbers. One ticket, last.

## Every ticket on the way (the repository's own checklist, `AGENTS.md`)

Hidden check from the ticket's *Expected* list; two arms (no devkb, devkb) from the base commit; **two-way PR review**; an Execution-result comment with the
numbers; graph misses reviewed. The two-way review earns its cost: on PR #404 it found four regressions the author's tests had missed (a ternary in a
`TEST` body read as an initialiser list; `#undef X` followed by `#define X` never expanded; a tuple-returning helper inside `try` losing its types; a
macro-name rule that was too broad), and a quadratic constructor-name filter that our corpus runs had not shown.

## Mistakes to avoid (all happened)

| symptom | cause | how it was found |
|---|---|---|
| 277 bogus edges on a C library | a C++-only scan ran on C code | corpus edge diff on every pinned repository |
| local variables stopped being typed | a new module-level regex reused an existing name (`_LOCAL`) | the existing tests |
| `#undef` never recorded | the pattern matched the directive's text without its `#undef` | the audit reproduction still failing |
| 31 real method edges removed | "a bare call that names a class is a constructor" with no check that every function of that name is a constructor | corpus edge diff |
| precision looked worse after a fix | the scorer counts an edge to a merged overload node as wrong | `split_wrong.py` |
| a "limit" in the README that did not hold | written from the ticket, not from a fixture | trying the shapes |
| build +19% on the big repository | three added scans, each cheap alone | profile against the previous release |

Always diff the edge set (removed, added) of every pinned repository before and after a change: removals are where regressions hide.

## Starting points for Java and Rust (proposed, not tried)

**Java.** Facts: packages and imports, classes, interfaces, enums, records, nested and anonymous classes, lambdas, generics, overloads, annotations. Tests:
JUnit 4 and 5 `@Test`, `@ParameterizedTest`, TestNG. Hazards: dispatch through interfaces and inheritance (many implementers), dependency injection and
reflection (Spring), Lombok-generated members (the same family as macro-generated definitions), annotation processors, generated sources under
`target/` or `build/`. Truth: the JDK's compiler tree API (`com.sun.source`) from a small program, or SCIP via `scip-java` (to verify); needs a build
classpath for the pinned repositories, so choose repositories that compile with plain `javac` or Maven. Visibility rule to implement early: package and
import resolution, like include visibility in C/C++.

**Rust.** Facts: crates and workspaces (`Cargo.toml`), `mod` and `use` paths, `pub use` re-exports, `impl` blocks and traits, generics, closures, macros
(`macro_rules!`, derives, attribute macros). Tests: `#[test]`, `#[cfg(test)] mod tests`, `tests/` and `benches/`. Hazards: macros are the preprocessor problem
again (a definition a macro generates is not seen; start with a limit and a fixture, not a macro expander); `cfg` conditional compilation; method
resolution through auto-deref and trait dispatch; generated code under `target/`. Truth: `rust-analyzer scip` or its LSIF output (to verify), compiled with
`cargo check`; uncompilable crates are listed as not measured, as in C/C++. Visibility rule to implement early: `use` path and `mod` resolution.

For both, begin with Phase 0 and Phase 1 and stop there for review: a SPEC and a baseline table cost days; a wrong extractor built without them costs rounds.
