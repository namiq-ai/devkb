# C/C++ CALLS precision, adjudicated by hand (SPEC-DKB-004 story 1, #117)

Edge precision against the compiler truth is a lower bound: the truth cannot see calls inside uninstantiated templates,
behind annotation macros, or in generated test classes, and it used to drop recursion. This sample measures what an agent
cares about: **of the edges devkb 0.2.11 links, how many are right.**

## Method

- **Truth** (`bench/cpp/truth_clang.py`, libclang 18): keeps recursive calls; lists translation units with a fatal
  diagnostic (`not_compiled`, with the first diagnostic); excludes vendored paths named in `devkb/bench/cpp_corpus.json`
  (`vendored`). Builds: cJSON, tinyxml2 plain; fmt `-I include -I test/gtest`; leveldb `-I include` and googletest at the
  pinned submodule commit `a35bc7693c` (`-I <googletest>/googletest/include -I <googletest>/googlemock/include`).
- **Frame**: every CALLS edge devkb links between non-vendored files, excluding edges in or into a file the truth could
  not compile (`not_measured`). An edge is *truth-confirmed* if the truth has the (caller, callee) pair, *wrong by truth*
  if both ends are truth definitions and it has not, *unmapped* if an end has no truth definition.
- **Sample** (`bench/cpp/adjudicate.py draw`, seed **117**): the frame sorted by (caller, callee), then
  `random.Random(117).sample`, 100 edges per repository. Files: `cpp-samples/<repo>.jsonl`, one line per edge with the
  verdict and a note; the first line is the sampling metadata.
- **Verdicts**: truth-confirmed edges are recorded correct without being read. Every other sampled edge was judged by hand
  against the source (`adjudicate.py show` prints the caller's lines that name the callee and the callee's definition).
  *Correct* means the call in the caller's body can only mean that definition under C++ lookup (qualified name, the
  caller's class and bases, the receiver's declared type, ADL, namespace). **Overloads share one devkb symbol**
  (`XMLUtil::ToStr`, `detail::fill_n`), so a call to any overload of the linked name is correct; a call to a same-named
  function in another file, or a text that is not a call, is wrong.
- **Interval**: Wilson score, 95%.

## Result

| Repository | In-scope edges | Sampled | Truth-confirmed | Judged by hand | of which correct | **Adjudicated precision** | 95% interval |
|---|---|---|---|---|---|---|---|
| cJSON (C) | 808 | 100 | 100 | 0 | 0 | **1.000** (100/100) | 0.963 to 1.000 |
| leveldb (C++) | 2,033 | 100 | 85 | 15 | 15 | **1.000** (100/100) | 0.963 to 1.000 |
| fmt (C++, templates) | 1,427 | 100 | 24 | 76 | 69 | **0.930** (93/100) | 0.863 to 0.966 |
| tinyxml2 (C++) | 450 | 100 | 84 | 16 | 15 | **0.990** (99/100) | 0.946 to 0.998 |

Against the truth alone (`quality.py`, same edges): cJSON 1.000, leveldb 0.967, fmt 0.381, tinyxml2 0.814.

| Repository | cpp-qualified | cpp-same-class | cpp-same-class-base | cpp-same-file | cpp-typed-receiver | cpp-typed-receiver-base | cpp-unique-free | extern-c |
|---|---|---|---|---|---|---|---|---|
| cJSON |  |  |  | 35/35 |  |  | 65/65 |  |
| leveldb | 10/10 | 21/21 | 1/1 | 11/11 | 38/38 | 1/1 | 16/16 | 2/2 |
| fmt | 10/11 | 13/14 |  | 33/36 | 14/14 | 2/2 | 21/23 |  |
| tinyxml2 | 12/12 | 39/40 | 9/9 | 2/2 | 32/32 | 5/5 |  |  |

(correct / sampled, by edge source; about 100 edges per row, so no cell supports a claim on its own.)

**N1 (≥ 0.95)**: met by the point estimate and the interval's lower bound on cJSON and leveldb (0.963), by the point
estimate on tinyxml2 (0.990; lower bound 0.946), **not met on fmt** (0.930; the interval reaches 0.966).

## The 8 errors

| Repo | # | Edge | Why wrong |
|---|---|---|---|
| fmt | 34 | `copy_noinline` → `copy` (format.h) | `copy<OutChar>(begin, end, out)` has 3 arguments: `core.h`'s iterator `copy`, not `format.h`'s string-view `copy` |
| fmt | 39 | `fill` → `copy` | the same: `copy<Char>(data, data + n, it)` |
| fmt | 56 | `write_escaped_string` → `copy` | the same |
| fmt | 72 | `formatter.format` → `copy` (ranges.h) | the same, `detail::copy<Char>(sep.begin(), sep.end(), out)` |
| fmt | 73 | `join_view.join_view` → `begin` (ranges-test.cc) | `: begin(std::move(b))` initialises the data member `begin`; no call, and a test helper in another file |
| fmt | 79 | `memory_buffer_test.allocator` → `allocate` (format-inl.h) | `EXPECT_CALL(alloc, allocate(size))` names the mock's method; it is not a call |
| fmt | 99 | `test.dup2` → `test.dup2` | inside the definition of `test::dup2`, `::FMT_POSIX(dup2(...))` is the system `::dup2` |
| tinyxml2 | 51 | `XMLNode.DeleteNode` → `XMLNode.XMLNode` | `node->~XMLNode()` is a destructor call; the edge goes to the constructor |

Four of the eight are one cause (a same-named function in the caller's file chosen over the one the argument count
selects in another file: F5, story 4). Three are text read as a call.

## Where the truth is wrong and devkb is right (hand-judged correct, truth had no edge: 99 of 107)

- **Calls the compiler cannot resolve**: inside uninstantiated templates and on explicit template arguments
  (`RoundUp<4>(p)`, `max_value<uint32_t>()`, `write_exponent<Char>`, `count_digits<1>`, `thousands_sep_impl<char>`).
- **Annotation macros** hide the member from libclang: `locks_.Insert(filename)` after `LOCKS_EXCLUDED(mu_)` (leveldb).
- **Generated test classes**: a `TEST_F` body is a method of a class the truth names `X_Test`, devkb `X.Name`;
  calls inside are unmapped (`DBTest.MinorCompactionsHappen` → `Key`).
- **Calls in preprocessor variants** (`use_facet` in the `FMT_USE_LOCALE == 0` branch; `restore_and_read` under
  `_WIN32`).
- **Overloads**: devkb keeps one symbol per name, the truth one per USR, so a call to a sibling overload is "wrong".
  This is a measurement convention, written above, and a limit: devkb cannot tell overloads apart.

## Limits of this sample

- 100 edges per repository gives an interval about ±4 points at 1.0 and ±7 at 0.93; the frame is 450 to 2,033 edges.
- One reviewer (the implementing agent) judged all 107 hand edges; none was double-checked. The 8 errors and the
  judgments with a variant or overload note (`note` field of the JSONL) are the ones to re-read first.
- Truth-confirmed edges are assumed correct: a (caller, callee) pair the truth has can still be a wrong call site.
- The sample is of devkb 0.2.11 at these pinned commits (cJSON `6d9f2443ab`, fmt `57f1b5930d`, leveldb `29465588d3`,
  tinyxml2 `8224e427b6`). Any extractor change needs a new draw, not a re-use of these verdicts.

## Reproduce

```
python bench/cpp/truth_clang.py corpus/fmt truth_fmt.json -I include -I test/gtest
python bench/cpp/quality.py . corpus/fmt truth_fmt.json --examples
python bench/cpp/adjudicate.py draw . corpus/fmt truth_fmt.json fmt.jsonl --n 100 --seed 117   # a new draw
python bench/cpp/adjudicate.py show fmt.jsonl --repo corpus/fmt                                 # edges still without a verdict
python bench/cpp/adjudicate.py judge fmt.jsonl 12=correct:why 13=wrong:why
python bench/cpp/adjudicate.py report docs/specs/cpp-samples/*.jsonl --markdown                 # the tables above
```

## 0.2.15 adjudication, six repositories (#123, #124)

Seed 117, 100 edges per repository, `bench/cpp/samples/<repo>.jsonl` (the files `adjudicate.py` reads). Truth-confirmed edges are
recorded correct; the other sampled edges were judged by hand against the source.

| Repository | Frame | Correct / 100 | 95% interval | Judged by hand | Wrong |
|---|---|---|---|---|---|
| cJSON | 813 | 100 | 0.963-1.000 | 0 | 0 |
| Lua | 4,054 | 100 | 0.963-1.000 | 5 | 0 |
| autoas | 622 | 100 | 0.963-1.000 | 51 | 0 |
| leveldb | 1,754 | 100 | 0.963-1.000 | 1 | 0 |
| yaml-cpp | 1,453 | 100 | 0.963-1.000 | 16 | 0 |
| fmt | 1,415 | 99 | 0.946-0.998 | 60 | 1 |

By source over the six samples: `cpp-same-file` 161/162, every other source 100% (`cpp-unique-free` 161/161, `cpp-typed-receiver` 85/85,
`cpp-same-class` 71/71, `cpp-constructor` 40/40, `cpp-macro` 34/34, `cpp-qualified` 31/31, `extern-c` 7/7, `cpp-same-class-base` 5/5,
`cpp-typed-receiver-base` 4/4). The one wrong edge is fmt `for_each_codepoint -> copy`, a 3-argument call linked to the 2-argument overload in
the same file.

**The first round failed** (cpp-macro in Lua, fmt and autoas; fmt cpp-same-file; yaml-cpp cpp-constructor) and was fixed in the extractor, each fix with a
test: a macro expands only through definitions the calling file sees, and only to the callees every visible definition makes; a call through a
local `auto x = [` lambda is not linked; a name the file also brings in by `using` is not linked to its own same-file fallback; `T x(*this)` is a copy.
The samples were then redrawn from the fixed graph and every edge judged again, carrying earlier verdicts over for edges that were still there.

**Limit: one judge, who is not independent.** The agent that wrote the extractor drew the sample and wrote the verdicts (134 by hand in total), and two of
its first fmt verdicts were wrong and were corrected from the source. An independent re-judgement of those edges is still owed.
