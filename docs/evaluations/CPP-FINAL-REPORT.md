# C and C++ support in devkb: design, implementation and benchmark

Standardised report. Every table that describes agent runs has the same columns: **Turns, Model calls, Grep, File load, devkb** (calls per run), then the quality columns of that table, then **Tokens** (context processed / output) and **Cost** in dollars as the last two. Regenerate with `make_report.py`.

Exploratory: one model (Sonnet), one to two runs per arm, small corpora. Differences under about 30% in cost or under 0.05 in precision are noise.

## 1. Summary

- **The graph:** `devkb build` now reads C and C++ (standard library only): definitions, calls, test frameworks, error messages. On the compiler-checked repositories, edge precision is 0.98 (cJSON) and 0.90 (leveldb); recall is 0.32 and 0.51, limited mostly by calls that exist only through macro expansion.

- **Does devkb help the agent?** On chain questions ("who reaches this function?") yes: 37% cheaper at the median, the same recall, tighter lists, every run used devkb. On feature builds no measurable effect: the agents read and patch code through the shell and never called devkb in any build run.

- **Does the specification help?** It buys behaviours no unspecified build delivered, above all a pack that does not claim Complete when it cannot follow a call, at 3 to 4 times the cost. It did not make the call graph more accurate.


## 2. Arms and method

| Arm | What the agent had | Prompt |
|---|---|---|
| plain | search, read, shell; no graph | the original request (one paragraph of requirements) |
| devkb | the same, plus the devkb MCP server (`lean-pack`), the `AGENTS.md` instruction, and a pre-edit hook | the same request |
| devkb + specification | the same as devkb | the accepted SPEC-DKB-001, ADR and stories, built epic by epic |
| chain benchmark | plain against devkb (MCP + instruction) | one read-only question: list the production callers at any depth and the tests |

Quality is scored three ways, none by the agent: (1) the acceptance script fixed before the runs (the original prompt's contract); (2) a **compiler truth** built with libclang (cJSON 968 definitions and 2,922 call edges; leveldb 1,484 and 3,159), against which edge precision and recall are computed by `bench/cpp/quality.py`; (3) behaviour checks that do not depend on naming (`bench/cpp/behavior.py`: REQ = the owner's constraints, SPEC = the accepted decisions). devkb was proven connected before every devkb-arm run (server connected and one real `pack` call returned).

## 3. Design phase (BMAD)

| Step | Persona | Turns | Model calls | devkb | Wall | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|
| BA analysis 1 (no devkb graph) | BMAD analyst run headless | 9 | n/a | 0 | n/a | 384k / 15k | $0.42 |
| BA analysis 2 (devkb graph present) | BMAD analyst run headless | 8 | n/a | 0 | n/a | 359k / 13k | $0.34 |
| Architecture and ADR-DKB-001 | BMAD architecture, fast path | 46 | 29 | 1.0 | 6 min | 2.8M / 42k | $1.24 |
| SPEC-DKB-002, ADR-DEVKB-009, 14 stories, 2 tickets | BMAD product owner (Sofia) | 59 | 45 | 0 | 9 min | 4.6M / 77k | $1.85 |
| **Total** | | | | | | | **$3.85** |

The analysis grounded on a devkb graph was cheaper and had fewer warnings than the ungrounded one (3 warnings against 1; one fewer story). The readiness gate of the process tooling used for the design refused 3 of 5 stories (a cited evidence file outside the repository; a criterion that was neither a command nor Given/When/Then).

## 4. Build benchmark: adding C and C++ support

| Run | Arm | Wall | Turns | Model calls | Grep | File load | devkb | Acceptance | Suite | cJSON P / R | leveldb P / R | Behaviour REQ / SPEC | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plain-r1 | plain | 12 min | 65 | 46 | 10.0 | 15.0 | 0 | 29/30 | 294 | 0.98 / 0.32 | 0.92 / 0.57 | 4/5 / 4/8 | 5.1M / 80k | $1.84 |
| plain-r2 | plain | 21 min | 50 | 41 | 9.0 | 6.0 | 0 | 30/30 | 292 | 0.98 / 0.32 | 0.88 / 0.62 | 4/5 / 4/8 | 4.7M / 91k | $1.95 |
| devkb-r1 | devkb (MCP + instruction + Edit/Write hook) | 12 min | 39 | 37 | 11.0 | 2.0 | 0 | 30/30 | 289 | 0.99 / 0.32 | 0.91 / 0.57 | 4/5 / 4/8 | 4.3M / 82k | $1.78 |
| devkb-r2 | devkb (MCP + instruction + Edit/Write hook) | 14 min | 75 | 58 | 20.0 | 8.0 | 0 | 30/30 | 296 | 0.99 / 0.32 | 0.91 / 0.43 | 4/5 / 3/8 | 7.2M / 89k | $2.23 |
| devkb-r3 | devkb (+ Bash hook) | 17 min | 60 | 55 | 12.0 | 13.0 | 0 | 30/30 | 301 | 0.98 / 0.32 | 0.92 / 0.56 | 4/5 / 4/8 | 8.4M / 112k | $2.69 |
| devkb-r4 | devkb (+ Bash hook) | 14 min | 60 | 47 | 18.0 | 10.0 | 0 | 30/30 | 303 | 0.99 / 0.32 | 0.92 / 0.52 | 4/5 / 4/8 | 6.5M / 101k | $2.33 |
| spec-r1 | devkb + specification | 47 min | 163 | 119 | 37.0 | 27.0 | 0 | 21/30 | 327 | 0.98 / 0.31 | 0.90 / 0.51 | 5/5 / 8/8 | 27.9M / 186k | $5.93 |
| spec-r2 | devkb + specification | 47 min | 176 | 146 | 33.0 | 23.0 | 0 | 21/30 | 351 | 0.98 / 0.31 | 0.90 / 0.51 | 5/5 / 8/8 | 42.3M / 228k | $8.03 |
| impl | devkb + specification (SPEC-DKB-002, on top of PR 35) | 39 min | 203 | 158 | 48.0 | 37.0 | 0 | n/a | 404 | 0.98 / 0.32 | 0.90 / 0.51 | 5/5 / 8/8 | 39.7M / 201k | $7.48 |

Rows `plain`, `devkb` and `devkb + specification` implement the same request (the two specification rows implement the epic of six tickets, so they do more). The `impl` row implements SPEC-DKB-002 on top of the first implementation and is scored against its own stories, not the original acceptance script. The call counts are calls per run. P / R = edge precision / recall against the compiler truth.

Means by arm:

| Arm | Runs | Wall | Turns | Model calls | Grep | File load | devkb | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|
| plain | 2 | 16 min | 58 | 44 | 9.5 | 10.5 | 0.0 | 4.9M / 85k | $1.89 |
| devkb | 4 | 14 min | 58 | 49 | 15.2 | 8.2 | 0.0 | 6.6M / 96k | $2.26 |
| devkb + specification | 2 | 47 min | 170 | 132 | 35.0 | 25.0 | 0.0 | 35.1M / 207k | $6.98 |
| SPEC-DKB-002 implementation | 1 | 39 min | 203 | 158 | 48.0 | 37.0 | 0.0 | 39.7M / 201k | $7.48 |

### Behaviour checks (naming-independent)

| Check | prototype | plain | devkb | devkb + spec | SPEC-DKB-002 impl |
|---|---|---|---|---|---|
| REQ: R1 pack never says Complete while missing a pointer caller | pass | pass | pass | pass | pass |
| REQ: R2 ambiguous receiver not guessed | pass | pass | pass | pass | pass |
| REQ: R5 untyped receiver pack is Incomplete or lists the caller | fail | fail | fail | pass | pass |
| REQ: R3 dependencies unchanged | pass | pass | pass | pass | pass |
| REQ: R4 limits stated in readme | pass | pass | pass | pass | pass |
| SPEC: D2 pointer receiver with declared type is linked | pass | pass | pass | pass | pass |
| SPEC: D2 typed receivers resolve to their own class | fail | pass | 3/4 | pass | pass |
| SPEC: D3 gtest catch doctest boost cases found | pass | pass | pass | pass | pass |
| SPEC: D3 zephyr ztest found | fail | fail | fail | pass | pass |
| SPEC: D3 each case records its framework | fail | fail | fail | pass | pass |
| SPEC: D4 throw message traces to its function | fail | fail | fail | pass | pass |
| SPEC: D5 overloads carry overload count | fail | fail | fail | pass | pass |
| SPEC: D5 macro wrapped return type found | fail | pass | pass | pass | pass |

## 5. Chain benchmark: plain against devkb

Question: list every production function that can reach `F`, at any depth, and the test files that exercise it. Read-only. Truth: the compiler's text-visible call graph, production code only. Five questions, two repetitions per arm (20 runs). Listed = functions the agent named; precision is approximate (a real caller outside the text-visible truth counts as wrong), recall is solid.

| Question | Arm | Truth | Listed | Precision | Recall | Test files | Turns | Model calls | Grep | File load | devkb | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| leveldb `WriteRawBlock` | plain | 24 | 48 | 0.51 | 1.00 | 0.62 | 7.5 | 6.5 | 6.0 | 0.0 | 0.0 | 199k / 4k | $0.125 |
|  | devkb | 24 | 22 | 0.94 | 0.88 | 0.50 | 4.0 | 4.0 | 1.0 | 0.0 | 1.0 | 109k / 1k | $0.064 |
| leveldb `LogAndApply` | plain | 8 | 40 | 0.20 | 1.00 | 1.00 | 9.0 | 6.5 | 7.0 | 0.5 | 0.0 | 189k / 4k | $0.121 |
|  | devkb | 8 | 23 | 0.33 | 0.94 | 0.75 | 7.0 | 6.5 | 4.0 | 0.0 | 1.0 | 182k / 3k | $0.103 |
| leveldb `Footer::DecodeFrom` | plain | 35 | 57 | 0.61 | 0.99 | 0.60 | 12.5 | 9.0 | 10.0 | 1.0 | 0.0 | 330k / 7k | $0.229 |
|  | devkb | 35 | 47 | 0.67 | 0.90 | 0.40 | 20.5 | 13.5 | 10.0 | 1.0 | 6.5 | 413k / 6k | $0.179 |
| cJSON `print_value` | plain | 9 | 8 | 0.94 | 0.78 | 0.70 | 3.5 | 3.5 | 2.5 | 0.0 | 0.0 | 89k / 1k | $0.053 |
|  | devkb | 9 | 10 | 0.86 | 1.00 | 0.90 | 3.5 | 3.5 | 0.5 | 0.0 | 1.0 | 93k / 1k | $0.051 |
| cJSON `cJSON_Delete` | plain | 48 | 48 | 0.97 | 0.96 | 0.87 | 10.0 | 7.5 | 8.0 | 0.0 | 0.0 | 266k / 6k | $0.180 |
|  | devkb | 48 | 47 | 0.99 | 0.97 | 0.84 | 8.0 | 8.0 | 2.0 | 1.0 | 2.0 | 242k / 3k | $0.107 |
| **All 10 runs** | **plain** | | | 0.64 | 0.94 | 0.76 | 8.5 | 6.6 | 6.7 | 0.3 | 0.0 | 215k / 5k | $0.141 |
| **All 10 runs** | **devkb** | | | 0.76 | 0.94 | 0.68 | 8.6 | 7.1 | 3.5 | 0.4 | 2.3 | 208k / 3k | $0.101 |

Text returned to the model, mean per run: plain 19.7k (grep 18.4k), devkb 10.5k (grep 5.6k, devkb 4.3k). The number of tool calls is the same (7.5 and 7.6): devkb replaces about half of the greps with one or two pack calls.

Per run:

| Repo | Question | Arm | Run | Turns | Model calls | Grep | File load | devkb | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| leveldb | WriteRawBlock | plain | r1 | 10 | 8 | 8.0 | 0 | 0 | 260k / 5k | $0.176 |
| leveldb | WriteRawBlock | plain | r2 | 5 | 5 | 4.0 | 0 | 0 | 139k / 3k | $0.073 |
| leveldb | WriteRawBlock | devkb | r1 | 3 | 3 | 0 | 0 | 1.0 | 80k / 1k | $0.077 |
| leveldb | WriteRawBlock | devkb | r2 | 5 | 5 | 2.0 | 0 | 1.0 | 139k / 2k | $0.051 |
| leveldb | LogAndApply | plain | r1 | 5 | 5 | 4.0 | 0 | 0 | 137k / 3k | $0.116 |
| leveldb | LogAndApply | plain | r2 | 13 | 8 | 10.0 | 1.0 | 0 | 240k / 5k | $0.125 |
| leveldb | LogAndApply | devkb | r1 | 6 | 6 | 3.0 | 0 | 1.0 | 169k / 3k | $0.129 |
| leveldb | LogAndApply | devkb | r2 | 8 | 7 | 5.0 | 0 | 1.0 | 195k / 3k | $0.076 |
| leveldb | DecodeFrom | plain | r1 | 10 | 8 | 8.0 | 0 | 0 | 282k / 6k | $0.221 |
| leveldb | DecodeFrom | plain | r2 | 15 | 10 | 12.0 | 2.0 | 0 | 378k / 9k | $0.237 |
| leveldb | DecodeFrom | devkb | r1 | 24 | 16 | 8.0 | 2.0 | 11.0 | 494k / 6k | $0.216 |
| leveldb | DecodeFrom | devkb | r2 | 17 | 11 | 12.0 | 0 | 2.0 | 331k / 6k | $0.141 |
| cJSON | print_value | plain | r1 | 4 | 4 | 3.0 | 0 | 0 | 102k / 1k | $0.080 |
| cJSON | print_value | plain | r2 | 3 | 3 | 2.0 | 0 | 0 | 75k / 1k | $0.026 |
| cJSON | print_value | devkb | r1 | 3 | 3 | 0 | 0 | 1.0 | 79k / 1k | $0.072 |
| cJSON | print_value | devkb | r2 | 4 | 4 | 1.0 | 0 | 1.0 | 107k / 1k | $0.030 |
| cJSON | cJSON_Delete | plain | r1 | 10 | 8 | 8.0 | 0 | 0 | 297k / 6k | $0.209 |
| cJSON | cJSON_Delete | plain | r2 | 10 | 7 | 8.0 | 0 | 0 | 235k / 6k | $0.150 |
| cJSON | cJSON_Delete | devkb | r1 | 7 | 7 | 2.0 | 0 | 2.0 | 207k / 3k | $0.119 |
| cJSON | cJSON_Delete | devkb | r2 | 9 | 9 | 2.0 | 2.0 | 2.0 | 278k / 3k | $0.096 |

## 6. SPEC-DKB-002 (language profiles and cross-language boundaries): what was built

Built by one agent run (row `impl` above) from the accepted spec, ADR-DEVKB-009 and 14 stories, committed as `a20adb8` and `4fe9aa6` on `feat/cpp-language-profiles` (stacked on PR 35). Independent measurement of the result:

| Measure | PR 35 code | SPEC-DKB-002 branch |
|---|---|---|
| Suite | 341 passed | 404 passed (one test failed after the commit; fixed: it asserted the repository holds no C/C++ files and the new fixtures are C/C++) |
| cJSON edge precision / recall | 0.983 / 0.313 | 0.98 / 0.32 |
| leveldb edge precision / recall | 0.904 / 0.508 | 0.90 / 0.51 |
| Behaviour checks, REQ / SPEC | 5/5 / 8/8 | 5/5 / 8/8 |
| Pack for a JNI-named C function | "Complete", no caller | "Complete for the languages read (c, cpp, python). Callers may exist in languages not read (JNI)." |
| Pack for a C function called from Python with `ctypes` | the Python caller missed, "Complete" | the caller `use.py` listed, tagged `via ctypes` |
| autoas cross-language edges | 340 (extern "C", untagged) | 362: extern-c 340, pybind11 22 (Python to C++) |
| Zephyr build | 80 s | 95.5 s (inside the 120 s budget; 16% slower) |
| autoas build | 4.5 s | 5.1 s |
| Symbols by language, Zephyr | n/a | c 137,342; cpp 245 (it is a C repository); 26,990 symbols marked `abi_exported` |

Not run by the agent (no libclang in its environment): the dialect-fixture truth run and the compiler header-agreement report; the compiler-truth numbers above were measured afterwards by `bench/cpp/quality.py`. Two stories are partly done (1.5 dialect keywords against the compiler; 1.6 the C-profile fault test).

## 7. Measured limitations

| Limitation | Evidence |
|---|---|
| Calls produced by macros are invisible to a text scan | 1,901 of cJSON's 2,922 real call edges (65%) and 368 of leveldb's 3,159 (12%) exist only through macro expansion |
| Constructor calls are not linked | 16% of leveldb's missed edges |
| Typed-receiver method calls only partly linked | 14% of leveldb's missed edges before SPEC-DKB-002; recall is 0.51 |
| About 1 linked edge in 10 is wrong | leveldb precision 0.90 in every build |
| Test files found through fixtures and test macros are missed | devkb found fewer test files than grep on 3 of 5 chain questions (0.68 against 0.76) |
| `abi_exported` is broad | 26,990 of Zephyr's symbols (18%) would carry the foreign-callers note |
| Generated code and pre-processing | 394 Zephyr C files include generated headers, 4,955 use devicetree macros, 32 autoas Python scripts write C (ticket A) |
| Event-driven triggers (IRQ, timers, work queues, callbacks, IPC) | 2,147 Zephyr files register handlers through op tables, 1,072 touch IRQs, 52 autoas files use IPC (ticket B) |
| Orchestrated builds cannot call devkb tools | the implementation allowlist has no `mcp__*` entry; only a hook can reach them |
| No preprocessor expansion, overload resolution or type inference | stated in the README and in every C/C++ pack |

## 8. Abnormalities found, investigated, and what changed

| Abnormality | Cause | Action |
|---|---|---|
| The pre-edit hook never fired in 6 builds | agents used Edit/Write on an existing file in 0 of 6 builds; they read with cat/sed and patch with scripts through the shell | hook extended to the shell; real-Claude test passed; two re-measurement runs delivered packs, behaviour unchanged |
| `pack refactor Store.add` said "ambiguous" whenever two classes shared a method | `_resolve` kept only the last dotted component | fixed with a qualified-suffix match and a test |
| First accuracy check said 300 of 300, the compiler said about 10% wrong | the check only proved the callee's name appeared in the caller's file | compiler truth added; the proxy dropped |
| Compiler truth first showed 0.70 precision | libclang had no system headers, so one function got a different USR per translation unit | truth rebuilt with the compiler's include path (+26 to 34% edges) |
| Costs and turns were wrong in the first scoring | one `result` event per wake-up, each cumulative | totals from the cumulative `modelUsage` and the largest cost |
| A checker passed builds that lacked a feature | a fixture put the function name inside the error message; a check called an API the specified builds had moved | fixtures corrected, then all runs re-scored |
| The agent's "suite passes" was green and then red | it ran the suite before committing new C/C++ fixtures, and a test asserted the repository holds no C/C++ files | test now ignores `tests/fixtures`; 404 pass |
| A finished 39-minute run went unnoticed for 11 minutes | it was started without a completion monitor | monitors added |
| The specified builds fail the original acceptance script (21 of 30) | the ADR chose different names and moved test discovery into the graph | behaviour checks used instead; the spec should state compatibility |

## 9. Recommendations

1. Merge PR 35 after a person reviews `cpp_symbols.py` and `cpp_resolve.py`; it is agent-written and verified by tests and benchmarks, not by line-by-line review.
2. Improve edge quality where the compiler says it is lost: constructor calls, typed receivers, the 10% wrong edges; measure with `quality.py`.
3. Judge devkb on chain and impact questions, not on feature builds; there it is cheaper, equal in recall and tighter. Fix its test-file recall (fixtures and macros).
4. Narrow `abi_exported` only after the 18% figure is reviewed by the owner; a note on every exported C function may be too noisy.
5. Schedule the two spikes (generated code, event-driven triggers) after the Python to C and Kconfig work; both are large in Zephyr.
6. Keep BMAD alone for repositories of this size.

## 10. Reproduce

`bench/cpp/` in the PR (compiler truth, quality, behaviour), `bench/exercises/cpp/tool_usage.py` (tool counts), `bench/exercises/cpp/make_report.py` (this report). Corpus: cJSON, fmt, leveldb, autoas, Zephyr at the pinned commits; compiler truth needs `pip install libclang` and `g++`.

## 11. Grep analysis: what the agents search for and what the graph could answer



| Kind of grep | What the agent is trying to learn | Events | Text returned | Share of grep cost | Cumulative | Can the graph answer it? | What would answer it |
|---|---|---|---|---|---|---|---|
| filter the output of another command | trim the output of tests, git or a file read down to the lines it cares about | 49 (17%) | 14.5k | 30.1% | 30% | not a search | nothing: grep is a filter here, not a search |
| find where one symbol is defined | read a function or class: 90% add -A/-B/-C, i.e. they want the body, not the location | 31 (11%) | 8.2k | 14.7% | 45% | yes, data exists | a `symbol(name)` call returning signature, file and exact line range, with the source on request (the graph stores line_start and line_end) |
| outline: list the definitions and imports in a file | see the shape of a file before reading or editing it | 20 (7%) | 8.2k | 11.9% | 57% | yes, data exists | an `outline(file)` call: Symbols of the file with line ranges (the graph has them; `explain_area` shows only key symbols) |
| find the callers or users of a function or class the graph knows | who uses this function (impact of a change) | 16 (5%) | 6.4k | 11.7% | 68% | yes, today | `callers`, `pack(refactor)`: available now; the instruction tells agents to grep one-hop lookups |
| find text in docs, specs and tickets | check what the README, scope or spec says | 32 (11%) | 7.1k | 9.6% | 78% | partly | `find_docs` ranks specs/ADRs by topic; the text inside docs is not indexed |
| find uses of a module, key or name the graph has no node for | where is this module, import, key or argument name used | 48 (17%) | 4.9k | 7.9% | 86% | no, needs new data | new graph data: modules and imports as nodes with USES edges |
| find a string, phrase or pattern in code | locate code by an idiom or literal | 32 (11%) | 4.4k | 6.1% | 92% | partly | only error messages and env vars are indexed (ErrorSignature, ConfigKey) |
| find tests | which tests touch this | 15 (5%) | 2.6k | 3.5% | 96% | yes, today | `tests_for`, `tests_to_run`: available now |
| find uses of a constant or macro | where is this module-level constant or macro used | 8 (2%) | 2.3k | 3.3% | 99% | no, needs new data | new graph data: module-level constants and macros as nodes |
| search an external repository or a scratch file (no graph) | read the reference corpus or a temporary file | 13 (4%) | 1.2k | 0.9% | 100% | no, outside the graph | nothing: they are outside the repository being edited |
| count or check that something is present | verify an edit or a count | 11 (4%) | 0.2k | 0.1% | 100% | not a search | nothing: verification, not search |

**Reading the cost.** The cost is flatter than 80/20: it takes 6 of 11 kinds to reach 80% of grep cost. Two of the eleven kinds
(definition lookup and outline) are 27% of all grep cost (38% of the cost of real searches), and the four kinds the graph can already answer
from data it holds (adding callers and tests) are 42% (60% of searches). The 20% to pick is therefore the **definition and outline** pair: one need ("show me the code
structure and a symbol's body, with exact lines") and no schema change.

Cost here = text returned to the model, weighted by the model calls still to come (text stays in context). Events = 275 greps in 9 build runs.

### What the purposes are

1. **"Where is this defined" is really "show me this function"**: 28 of 31 definition greps add `-A`, `-B` or `-C` and read the lines after the match (`grep -n "def _tests_of" -A25 devkb/process_api.py`).
   The graph stores the exact range of all 1,020 Symbols (`line_start`, `line_end`), while the agents guess the length: the median function is 8 lines, so a fixed `-A25` over-reads 87% of functions and cuts 11% short.
2. **Outline is navigation before an edit**: `grep -n "^def \|^class " file.py | head`. The graph holds the same list with line ranges.
3. **Callers are the one need devkb already serves**, and the instruction tells agents to grep one-hop lookups. In the chain questions the same need is the main grep: the plain arm made 84 greps (41 of them caller lookups, 27k tokens of text),
   the devkb arm 38 greps (24 caller lookups, 9.8k tokens).
4. **A quarter of the cost is not searching at all**: grep as a filter on test output, git output, or a `cat file | grep` (11 events, 9.4k of the 14.5k tokens: reading part of a file).
5. **11% of the cost looks up things that are not nodes**: modules and imports (`cpp_symbols`, `framework`), module-level constants (`_PY_TEST`, `_JS_TEST`). The graph has only function, class and method Symbols.

### Which 20% to pick

The cost is flatter than 80/20 (6 of 11 kinds reach 80%). The best 20% is the **definition + outline pair: 27% of all grep cost (38% of the cost of real searches)**, a single need ("show me the structure and the body of this thing, with exact lines")
that the graph can answer from data it already holds. Adding callers and tests (already available) the graph covers 42% of the cost (60% of real searches). Nothing else is cheap to add:
docs and phrase search are only partly indexed, modules and constants need new nodes (11% of the cost), and 30% is not a search.

Proposed, in this order:
1. `outline(file)`: the Symbols of a file, kind and line range, optionally with docstring summaries (data exists; no schema change).
2. `symbol(name)`: signature, file and exact range, with the source of the range on request, bounded by the graph's own `line_end` instead of a guessed `-A25` (data exists; no schema change).
3. Put both in the default `lean-pack` toolset and add one line to the instruction ("to read a function, ask `symbol`, not grep -A").
4. Later, if wanted: modules, imports and module-level constants as nodes (needs schema, ADR-gated), 11% of the cost.

Not measured: whether agents would call the new tools (in four earlier rounds they ignored extra tools; the chain questions show they do use devkb when the tool matches the question), and the token saving. The first needs a rerun of a build with the tools added;
the second can be estimated from the 31 definition greps (8.2k tokens) and 20 outlines (8.2k tokens): up to 27% of grep text is the ceiling.
