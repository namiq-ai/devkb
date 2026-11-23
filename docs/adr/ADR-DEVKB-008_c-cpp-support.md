---
id: ADR-DEVKB-008
title: "ADR-DEVKB-008: C and C++ support in the graph"
type: adr
status: accepted
created: 2026-11-16
updated: 2026-11-16
owner: TL
supersedes: []
superseded_by: null
implements: SPEC-DKB-001
tickets: [DKB-001, DKB-002, DKB-003, DKB-004, DKB-005, DKB-006, DKB-007]
---

# ADR-DEVKB-008: C and C++ support in the graph

**Status**: Accepted by the factory owner's delegate on 2026-11-16. D1–D6 below are the TL's decisions of 2026-11-16, recorded as given. The `RAISES` description
and the Symbol property table in `devkb/ontology.md` change under this ADR, and `ADR-SDP-DEVKB-001` allows that only
through an Accepted ADR: this ADR must be Accepted before DKB-005's pull request merges. Items tagged
`[ASSUMPTION]` were inferred from the repository, not stated by the TL.

The decisions D1-D6 resolve the open questions of the specification SPEC-DKB-001. `DKB-002` to `DKB-007` are the
story and task ids of the project board this was built from; their acceptance evidence is the test files named
`tests/test_devkb_cpp_*_dkb00N.py`.

## Decisions

| Id | Decision |
|---|---|
| D1 | No earlier prototype C/C++ extractor is reused. Implement fresh from the spec, standard library only. |
| D2 | A method call on a receiver links only when the receiver's declared type is provable from a declaration in scope (parameter, local, member, `this`) and that type is a repository class with that method. Otherwise it is an unresolved call, never guessed by name uniqueness. A bare call links to: the same class, then a free function defined in the same file, then a repository-unique free function; never a C library name across files; never another class's method. |
| D3 | Frameworks: GoogleTest, Catch2, doctest first; Boost.Test, Unity, Zephyr ztest second. Each test case records its framework. |
| D4 | Literal messages in `throw` and `assert(cond && "msg")` are `RAISES`; literal strings passed to log and error macros are `LOGS`; existing `ErrorSignature`. Error-return codes are excluded and stated as unattributed. |
| D5 | One node per qualified name carrying `overload_count`. A macro-wrapped return type (an all-caps wrapper before the return type) is skipped when finding a definition's name. |
| D6 | Pinned corpus (cJSON, fmt, leveldb, autoas, Zephyr; shallow clones allowed), a build-time budget check, an unchanged-dependencies check, an independent regex edge truth. Kept separate from the Python agent benchmark. |

## 1. Module boundaries

| File | Does | Must not |
|---|---|---|
| `devkb/cpp_symbols.py` | `CXX_EXTS`, `is_cxx_path`, `CXX_LIMITS_TEXT`; `git ls-files` listing and skip rules; masking of comments, strings, character literals and `#if 0`; definition, call-site, declaration-table, indirect-reference, error-site and test-case records. Text in, records out. | import `devkb.model`, `build_symbols` or `cpp_resolve`; hold mutable module state |
| `devkb/cpp_resolve.py` | The call-resolution order (§3) and the C library denylist. Records in, `(edges, unresolved)` out. | read files; import the graph |
| `devkb/cpp_graph.py` | `add_to_graph(g, repo_root, error_sig_key)`: runs extract and resolve, writes `File`, `Symbol`, `DEFINED_IN`, `CALLS`, `RAISES`, `LOGS`, `ErrorSignature`; aggregates coverage properties over C/C++ symbols only. | be imported by `cpp_symbols` or `cpp_resolve` |
| `devkb/build_symbols.py` | One call to `cpp_graph.add_to_graph`, after the Python and TypeScript passes, passing the existing `_error_signature_key`. | gain any other C/C++ logic |
| `devkb/test_discovery.py` | C/C++ test-file patterns, the macro-to-framework table, `tests_in_file` for C/C++. | choose a framework outside the table |
| `devkb/extractors/test_inventory.py` | `TestCase` and `DEFINED_IN` from discovery; `framework` taken from discovery. | hard-code `pytest` or `js` for a C/C++ file |
| `devkb/process_api.py` | `is_test_path` learns C/C++ test paths; `_coverage` reads `incomplete_reasons`, `unattributed_errors`. | resolve or guess calls |
| `devkb/packs.py` | Prints the limit statement for a C/C++ symbol; prints **Incomplete** reasons. | print the limit statement for a non-C/C++ symbol |
| `devkb/ontology.md` | `RAISES` description; Symbol property table (§2). | gain a node type or verb |
| `devkb/bench/cpp_corpus.json` | Corpus pins, floors, reference machine, budgets. | |
| `devkb/bench/cpp_corpus.py` | Fetch pinned clones to a cache directory outside the repository; precision/recall/Complete check; budget check; dependency check. | be imported by `devkb/` runtime code |
| `devkb/bench/cpp_truth.py` | Independent regex truth. | import anything from `devkb` (a test scans its imports) |

Dependency direction: `cpp_symbols` → `cpp_resolve` → `cpp_graph` ← `build_symbols`. `cpp_symbols` also feeds `cpp_graph`.

## 2. Data contract

**Files.** `.c .h .cc .cpp .cxx .hh .hpp .hxx`, tracked by git. Skipped: `third_party`, `thirdparty`, `vendor`, `external`, `build` and `cmake-build-*` path segments; `*.pb.h`, `*.pb.cc`, `*.generated.*`; any file over 2 MB (recorded in `manifest.json` under `cpp.skipped`, and it sets `unread-file` on every C/C++ symbol). `[ASSUMPTION]` the 2 MB cap and the skip list, inferred from the REPORT.md libstdc++ and Zephyr runs. A `.h` file is read as C++ when its masked text holds `class`, `namespace`, `template` or `::`, else as C.

**`File` node**: `source="cpp-symbols"`, natural key the repo-relative path.

**`Symbol` node**: natural key `<path>::<qualified_name>`; `source="cpp-symbols"`.

| Property | Value |
|---|---|
| `kind` | `function` (free, including C `static`), `method`, `class` (class, struct, union), `enum` (enum, enum class), `test` (one per test-case body) |
| `qualified_name` | class chain joined with `.`: `Block.Iter.Next`, `Table.operator==`, `Table.~Table`, `Table.Table`. Out-of-line `Table::Add` is `Table.Add`. A namespace is not part of it unless two symbols of one file collide, then both take the namespace prefix. |
| `namespace` | the namespace chain joined with `::`, or absent |
| `line_start` | 1-based line of the name in the definition (first definition when overloaded); the text at that line contains the short name |
| `line_end` | closing-brace line, else `line_start` |
| `overload_count`, `overload_lines` | ≥ 1; all definition lines of the key in this file, at most 20 |
| `is_public` | false for `static`, anonymous-namespace and `private`/`protected` members; else true |
| `docstring_summary`, `decorators` | `null`, `[]` (same shape as TS symbols) |
| `unresolved_calls`, `unresolved_files`, `unresolved_file_count` | as today (`ontology.md`), computed over C/C++ symbols and C/C++ call sites only |
| `incomplete_reasons` | sorted subset of `dynamic-dispatch` (method declared `virtual` or `override`, or overriding or overridden in the repository), `implicit-call` (constructor, destructor, operator), `unread-file` |
| `unattributed_errors` | count of `throw` and `assert` sites in the body whose message is not a literal (§6) |
| `framework` | on `kind="test"` only |

A declaration without a body creates no `Symbol`. A forward declaration creates none.

**Edges.** Every edge carries `source`, `confidence`, `evidence_ref` (`<path>:<line>` or `<caller> calls <callee>`).

| Verb | `source` | Confidence | When |
|---|---|---|---|
| `DEFINED_IN` Symbol → File | `cpp-symbols` | 1.0 | each definition |
| `CALLS` | `cpp-same-class` | 0.8 | bare call or `this->f()` to a method of the caller's own class |
| `CALLS` | `cpp-same-class-base` | 0.7 | same, found on an in-repository base class |
| `CALLS` | `cpp-same-file` | 0.8 | bare call to a free function the caller's file defines |
| `CALLS` | `cpp-qualified` | 0.9 | `Q::f()` where `Q.f` or the free `Q::f` matches exactly one repository symbol; `std::` and other known external roots are ignored |
| `CALLS` | `cpp-typed-receiver` | 0.7 | receiver type provable (§3 step 4) and the class has the method |
| `CALLS` | `cpp-typed-receiver-base` | 0.6 | same, through an in-repository base |
| `CALLS` | `cpp-unique-free` | 0.6 | bare call to a repository-unique free function in another file |
| `RAISES` | `cpp-throw` | 0.9 | literal in `throw` |
| `RAISES` | `cpp-assert` | 0.8 | literal in `assert(cond && "msg")` |
| `LOGS` | `cpp-log-macro` | 0.85 | literal in a recognised log or error macro |

`[ASSUMPTION]` the confidence values are ordered to the existing Python scale (same-file 0.8, cross-file 0.7, typed 0.6); the TL has not set them. `Symbol → ErrorSignature` uses the existing `_error_signature_key(kind, label, message)`.

## 3. Call-resolution order

For a call site (caller symbol `C` in file `F`, callee name `N`, form), the first rule that proves a target wins; a call that no rule proves is unresolved (§4), and no later rule may guess.

1. **Qualified** `Q::N(...)`: exactly one repository symbol whose qualified name ends `Q.N`, else step 6. A root of `std`, `boost`, or another name with no repository symbol is ignored (not counted).
2. **Bare** `N(...)`, caller is a method of class `K`: `K.N`, then `N` on `K`'s in-repository bases (`cpp-same-class-base`).
3. **Bare**, then: a free function `N` defined in `F` (`cpp-same-file`). A C `static` function wins over ten same-named functions elsewhere.
4. **Member** `recv.N(...)` or `recv->N(...)`: `this` goes to step 2 without the free-function fallback. For an identifier `recv`, look up its declaration in this order: a parameter or local variable of `C`, then a member of `C`'s class. The declared type must be written `T`, `T*`, `T&`, `T&&` or `const` forms of them, and `T` must match exactly one repository class that has a method `N` (own, else through a base). `auto`, a typedef or `using` alias, a template or smart-pointer wrapper, a global, a call result (`a().N()`), an index (`v[i].N()`), or an ambiguous `T` all fail the step.
5. **Bare**, then: a free function `N` that is the only free function of that name in the repository, and `N` is not in the C library denylist (`cpp-unique-free`).
6. **Unresolved**: if `N` is the short name of any C/C++ symbol, add `(file, caller, N)` to unresolved. Otherwise ignore the call.

Never: a bare call to another class's method; a denylisted C library name (`exit`, `abort`, `memcpy`, `memset`, `strlen`, `printf`, `malloc`, `free` and the rest of the closed list in `cpp_resolve.py`) linked across files, with one exception (amended 2026-11-23, #123): a bare call from a C file to a denylisted name that the repository defines exactly once, in a C file with external linkage, links to that definition (source `cpp-unique-free`) unless the caller lies under a host-side directory (`tools`, `test`, `util`, `example`, `sample`, `bench`, `fuzz` and their plurals), whose programs use the system's library; a link made because a method name is unique or is not a standard-library name. A call to a name defined by `#define` is a macro use, not a call: no edge, not counted. Self-recursion is an edge only when the rule above proves it.

An indirect reference (a repository function's name used without `(` after it, outside its own declaration and definition: `&f`, `.handler = f`, `{f, g}`, an argument, or inside a `#define` body) is added to unresolved for that name, in the file that holds it.

## 4. When a pack may say Complete

A C/C++ symbol `S` is **Complete** only when all hold:

1. `unresolved_calls` is 0 for `S`'s short name over C/C++ call sites, indirect references included. Several symbols sharing the name share the count, as today.
2. `incomplete_reasons` is empty.
3. `S`'s file path is a C/C++ path (the rule is not applied to Python).

Complete then reads: every call site of this name **visible in source text** was attributed to a target. It does not mean no runtime caller. Vendored, generated and oversized files are not read; the limit statement says so. `process_api._coverage` returns `complete: False` when either `unresolved_calls` or `incomplete_reasons` is set, and adds `reasons` to the reply; `packs.py` prints **Incomplete** with the reason. The rule for Python symbols is unchanged. `[ASSUMPTION]` `incomplete_reasons` and indirect-reference counting go beyond what D2 states; they follow the spec's GAP-3 ("never claim Complete when the graph could not follow a call").

`CXX_LIMITS_TEXT` is printed after the coverage line of every C/C++ pack, Complete or not, and states: no preprocessor expansion, no overload resolution, no type inference; vendored and generated paths not read; error-return codes not attributed.

## 5. Test-inventory contract

- A C/C++ file is a test file when its path matches `*_test.*`, `test_*.*`, `*_tests.*`, or it is under `test/`, `tests/` or `unittests/`, **or** its masked text contains a macro of the table below; either way a case needs the macro. A vendored path is skipped.
- Detection runs on masked text, so `TEST` in a comment, string or `#if 0` yields nothing.

| `framework` | Tier | Macros → case | Proof required |
|---|---|---|---|
| `gtest` | 1 | `TEST`, `TEST_F`, `TEST_P`, `TYPED_TEST`, `TYPED_TEST_P` → `Suite.Name` | none beyond the macro form |
| `catch2` | 1 | `TEST_CASE`, `SCENARIO`, `TEMPLATE_TEST_CASE` → the literal name | include of `catch2/` or `catch.hpp` |
| `doctest` | 1 | `TEST_CASE`, `SCENARIO` → the literal name | include of `doctest/` |
| `boost-test` | 2 | `BOOST_AUTO_TEST_CASE`, `BOOST_FIXTURE_TEST_CASE`, `BOOST_AUTO_TEST_CASE_TEMPLATE` → name | none beyond the macro form |
| `unity` | 2 | `RUN_TEST(fn)` → `fn`, at `fn`'s definition line when in the same file, else the `RUN_TEST` line | include of `unity.h` |
| `ztest` | 2 | `ZTEST`, `ZTEST_F`, `ZTEST_USER`, `ZTEST_USER_F` → `suite.name`; legacy `ztest_unit_test(fn)` → `fn` | include of `ztest.h` |

- A `TEST_CASE` with neither include is skipped and counted in `manifest.json` under `cpp.tests_skipped_ambiguous`.
- Each case is a `TestCase` node: key `<path>:<line>`, properties `file`, `line`, `function`, `framework`; `DEFINED_IN` → `File` (`source="test-inventory"`, confidence 1.0), exactly the existing shape. `pytest` and `js` output is byte-identical.
- Each macro body also becomes a `Symbol` of `kind="test"` in the same file (`qualified_name` = the case name, `framework` set), so §3 resolves its calls under the same rules. `tests_to_run` already counts `CALLS` from a test path, so the only `process_api` change is that `is_test_path` accepts C/C++ test paths. A test whose calls the resolver cannot prove is not linked; that is accepted (precision first).
- `run` is `""` for C/C++ (no build-system integration); the reply carries the existing "no tests linked; run the full suite" note when nothing links.

## 6. Error-extraction contract

| Construct | Result |
|---|---|
| `throw T("lit")`, `throw T{"lit"}`, `throw "lit"`, adjacent literals concatenated | `RAISES`, `ErrorSignature` kind `raised`, label `T` (`"literal"` for a bare literal), `message_template` the literal text verbatim, placeholders (`%d`, `{}`) unchanged |
| `assert(cond && "lit")` | `RAISES`, kind `raised`, label `assert`, message the literal |
| a recognised log or error macro with a literal first string argument | `LOGS`, kind `logged`, label the macro name, message the literal. The closed macro table sits in `cpp_symbols.py`: `LOG_ERR`, `LOG_WRN`, `LOG_ERROR`, `LOG_WARN`, `LOGE`, `LOGW`, `ERR`, `ERROR`, `pr_err`, `pr_warn`, `perror`. A name is added only with a fixture. `[ASSUMPTION]` the table is inferred from Zephyr, AUTOSAR and the Linux style, not from the TL. |
| `throw T(msg)`, `throw T(a + b)`, `assert(cond && msg)` with a non-literal | no signature; the enclosing Symbol's `unattributed_errors` increases; `pack` coverage text says so |
| bare `throw;` (rethrow), `static_assert`, stream macros (`LOG(ERROR) << ...`) | ignored |
| `return -EINVAL`, `return E_NOT_OK`, `return Status::Corruption("lit")` | excluded: no edge, no counter; the limit statement says error-return codes are unattributed |

The enclosing function is the nearest enclosing `Symbol` (a `test` Symbol included). `ontology.md`: only the `RAISES` description (adds C/C++ constructs) and the Symbol property table (§2 properties) change; no node type or verb is added.

## 7. Verification contract

- **Corpus.** `devkb/bench/cpp_corpus.json` pins `{name, url, commit}` with the full 40-character commit for cJSON, fmt, leveldb, autoas and Zephyr. `docs/evaluations/CPP-EVALUATION.md` records short hashes only (`6d9f244`, `57f1b59`, `2946558`, `cc37096`, `7cd4b562b`); DKB-006 resolves each to the full hash at first clone and commits it. A shallow clone (`--depth 1`, then fetch the pinned commit) goes to a cache directory outside the repository (`DEVKB_CPP_CORPUS`, default `~/.cache/devkb/cpp-corpus`). The check exits non-zero when `git rev-parse HEAD` differs from the pin.
- **Independent truth.** `bench/cpp_truth.py` finds, by regex over masked text, every definition and every call-site line of a name. A call site is **determinate** when the name has exactly one definition in the repository, or the site is spelled `Class::name(`, or the callee is a `static` function of that file. Caller precision is measured on determinate sites only; the number of indeterminate sites is reported beside it, never folded in. `[ASSUMPTION]` without type inference the truth cannot decide an overloaded or shared method name; this is the strongest check available that shares no code with the extractor.
- **Sample.** Fixed seed, 100 target functions per repository (all, if fewer), at least half with a name defined more than once. `[ASSUMPTION]` the sample size.
- **Complete rule.** For every sampled symbol whose pack says Complete, every determinate true caller site is in a caller the pack lists (matched by file and the caller symbol's `line_start..line_end`). Any miss exits 1. This floor is 1.0 and is not tunable.
- **Floors.** Precision and recall per repository are checked against `floors` in `cpp_corpus.json`. `[ASSUMPTION]` initial precision floor 0.95; the recall floor is set by QA to the first measurement minus 0.02 and committed with that measurement. Floors move up only.
- **Budget.** Wall time of `build_symbols.build`, best of two runs: Zephyr (15,912 C/C++ files) under 120 s; a corpus repository of about 100 files (cJSON) under 5 s. `reference_machine` (CPU, cores, disk) is recorded in `cpp_corpus.json`; it is an open question until QA states it.
- **Dependencies.** The check fails if `pyproject.toml` `dependencies` is not `["pyyaml>=6"]`, or if any `devkb/**/*.py` imports a module outside `sys.stdlib_module_names`, `yaml` and `devkb`.
- **Unchanged output.** A repository with no C/C++ file builds a byte-identical `nodes.jsonl` and `edges.jsonl` before and after (this repository and a Python fixture).
- **Seeded fault.** A test clears the denylist in `cpp_resolve` for its own run on a two-file fixture and asserts the check exits 1. No production flag injects a fault.
- **Separation.** `make cpp-check` runs the corpus check; it is not part of `make gate-1` or `make gate-2`, which stay offline. The fixture-based tests run in gate-2. `docs/BENCHMARK.md` and the Python benchmark runners are not edited.

## 8. Stories → modules and acceptance evidence

| Story | Modules touched | Acceptance evidence (command or artefact) |
|---|---|---|
| DKB-002 definitions | `cpp_symbols.py`, `cpp_graph.py`, `build_symbols.py` (one call), `tests/fixtures/cpp/`, new test file | pytest asserting the exact set of `(kind, qualified_name, line_start)` for a fixture (C function, C `static`, class, namespace, operator, constructor with member initialiser, macro-wrapped return type, enum, overloads with `overload_count`); fixture line `namespace std _GLIBCXX_VISIBILITY(default) {` yields no function; for every fixture symbol the text at `line_start` contains the short name; `git diff main -- pyproject.toml` empty on `dependencies`, and `python -c "import devkb.build_symbols"` in a venv with only `pyyaml`; `make gate-1`, `make gate-2` output with coverage ≥ 50% |
| DKB-003 calls and Complete | `cpp_symbols.py` (call-site, declaration, indirect-reference records), `cpp_resolve.py`, `cpp_graph.py`, `process_api._coverage`, `packs.py` | pytest on fixtures: `p->Add()` of unknown type → `callers("Table.Add")` has `complete: False`, `unresolved_calls ≥ 1`, calling file in `search_files`; forbidden-edge test (bare call in class A to same-named method of B; `exit`, `memcpy`, `printf` across files); required-edge test (C `static` function linked within its file while ten other files define the name); `file_map_.end()` not linked to a repo `end`; rendered pack text contains "Incomplete" and not "Complete."; each §4 reason has a fixture; `tests/test_devkb_call_resolution_odsf305.py` passes unchanged; `make gate-2` output |
| DKB-004 tests | `test_discovery.py`, `extractors/test_inventory.py`, `process_api.is_test_path`, `cpp_symbols.py` (test-case records), `cpp_graph.py` (`test` Symbols) | pytest: one fixture test per framework in §5 gives one `TestCase` with correct `file`, `line`, `function`, `framework`; `tests_to_run(files=[source file])` includes the test file; `TEST` in a comment or string yields none; the ambiguous `TEST_CASE` is skipped and counted; Python/JS `TestCase` rows byte-identical (diff of `nodes.jsonl` filtered to `TestCase`, before and after) |
| DKB-005 errors | `cpp_symbols.py` (error-site records), `cpp_graph.py`, `build_symbols.py` (passes `_error_signature_key`), `ontology.md`, `process_api._coverage`, `packs.py` | pytest on fixtures: `throw std::runtime_error("block checksum mismatch")` gives `RAISES` and `return Status::Corruption("block checksum mismatch")` gives none; `pack(kind="error", subject="block checksum mismatch")` ranks the raiser first and lists no symbol without the string; `throw Err(msg)` creates no `ErrorSignature` and the pack coverage text counts it; `git diff -- devkb/ontology.md` limited to the `RAISES` description and the property table; this ADR Accepted and linked in the PR |
| DKB-006 verification | `bench/cpp_corpus.json`, `bench/cpp_corpus.py`, `bench/cpp_truth.py`, `Makefile` (`cpp-check`), tests | `make cpp-check` output per repository (precision, recall, indeterminate count) and exit code; refusal on a wrong commit; the seeded-fault test exits 1; the budget lines with `reference_machine`; the dependency check; the Complete-recall result; the import-scan test of `cpp_truth.py`; the unchanged-output diff |
| DKB-007 docs and limits | `README.md`, `cpp_symbols.CXX_LIMITS_TEXT`, `packs.py`, `ontology.md` (property table), a test file | `grep -n "C, C++" README.md` shows its own row with "Partial" naming the three limits; a rendered C++ fixture pack contains the limit text and a rendered Python pack does not; a test reads each limit named in the README and asserts a fixture demonstrates it |

Order: DKB-002 → DKB-003 → DKB-004 and DKB-005 in parallel → DKB-006 (the harness can start after DKB-002, the Complete check needs DKB-003) → DKB-007 last, because it reads what the others print. The story that first touches a shared file (`packs.py`, `process_api.py`, `ontology.md`) owns the edit; later stories add to it, never rewrite.

## Consequences

- Recall on C++ methods falls against the prototype: Zephyr's 99,595 "unique name in the repository" edges were mostly links D2 now refuses. The price is more **Incomplete** packs; the gain is that **Complete** can be trusted. DKB-006 reports the recall that results, rather than a target set in advance.
- `unresolved_calls` for a C/C++ name now includes indirect references, so a callback-registered function (Zephyr) is Incomplete.
- One node per overload means a pack for an overloaded method lists callers of all its overloads.
- The three stated limits remain: no preprocessor expansion, no overload resolution, no type inference.

## Open

- Reference machine for the budgets (QA, DKB-006).
- Whether the TL accepts the confidence values and the `incomplete_reasons` set tagged `[ASSUMPTION]` above.
