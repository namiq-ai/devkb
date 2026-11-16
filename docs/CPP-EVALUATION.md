# C/C++ support: design to benchmark

Written 2026-11-16. Exploratory: one to two runs per arm, one model (Sonnet), so differences under about 30% in cost are
noise. The scoring scripts are in `bench/cpp/`; the run transcripts are kept by the maintainers.

## 1. What was run

| Phase | How | Result |
|---|---|---|
| Register | `make onboard` of a clone as project **DKB** (8701/4700), `ai_policy` `internal` (public OSS) | router allows the Claude CLI |
| Requirement | REQ-001 through the project's PMS | BA analysis by the daemon |
| Analysis | BA run 1 without a devkb graph, run 2 with one | run 1: $0.42, 7 stories, 3 warnings. run 2: $0.34, 6 stories, 1 warning, 5 spec nodes injected |
| Specification | approval creates `SPEC-DKB-001`, epic `DKB-001`, stories `DKB-002..007` | TL decisions D1-D6 answered the spec's open questions |
| Architecture | `bmad-architecture` (Fast path), devkb tools available | `ADR-DEVKB-008` + spine, $1.24, 46 turns, 1 devkb call |
| Readiness | `gate-0` | refused 3 of 5 stories until two TL edits (a cited file, a criterion wording) |
| Build | six headless agents on the same base, three arms | section 3 |
| Re-measure | two more devkb runs after the hook fix | section 5 |

Design-phase cost: about $2.0 of agent time, plus 2 TL edits and 3 manual workarounds (section 6).

## 2. Limitations of the C/C++ support, measured

Scored against a **compiler truth** (libclang: cJSON 968 definitions / 2,922 call edges; leveldb 1,484 / 3,159), not a
proxy. My first proxy ("the callee's name appears in the caller's file") said 300/300; the compiler says precision is 0.88-0.98.

| Limitation | Evidence |
|---|---|
| Calls produced by macros are invisible to a text scan | 1,901 of cJSON's 2,922 edges (65%) exist only through macro expansion (the Unity test macros); 368 of leveldb's 3,159 (12%) |
| Constructor calls are not linked | 519 of leveldb's missed edges (16% of all) |
| Method calls on a typed receiver (`p->Add()`) | 435 missed (14%); the best build still links only 56% of leveldb's edges |
| Precision is not "first" | 0.88-0.92 on leveldb: about 1 linked edge in 10 is wrong |
| No preprocessor expansion, no overload resolution, no type inference | stated in the spec, README and packs (D5/DKB-007) |
| Large repositories | Zephyr: 15,912 files, 44.8 s (24 s C/C++), 127,521 symbols |
| Files with no symbols | 14-28% of files per repository (declaration-only headers) |
| Error extraction and the **Complete** flag | prototype and the unspecified builds say Complete while missing a caller (section 4, R5) |
| Orchestrated builds cannot call devkb tools | ODSF's implementation allowlist has no `mcp__*` entry; only a hook can reach them |

## 3. Benchmark: three arms

Same base commit, same model, same acceptance script (sha256 fixed before the runs). Arms: **plain** (no devkb),
**devkb** (instruction + MCP server + pre-edit hook, original prompt), **devkb + spec** (same, plus the accepted spec, ADR
and tickets; its prompt asks for the whole epic). Cost is the run's cumulative `total_cost_usd`; tokens are the cumulative
`modelUsage`.

| Run | Cost | Wall | Output tok | Cache read | Acceptance | Suite |
|---|---|---|---|---|---|---|
| plain-r1 | $1.84 | 11.9 min | 80k | 5.0M | 29/30 | 294 |
| plain-r2 | $1.95 | 21.0 min | 91k | 4.5M | 30/30 | 292 |
| devkb-r1 | $1.78 | 11.7 min | 82k | 4.2M | 30/30 | 289 |
| devkb-r2 | $2.23 | 14.1 min | 89k | 7.1M | 30/30 | 296 |
| devkb-r3 (Bash hook) | $2.69 | 17.4 min | 112k | 8.2M | 30/30 | 301 |
| devkb-r4 (Bash hook) | $2.33 | 13.7 min | 101k | 6.3M | 30/30 | 303 |
| **spec-r1** | $5.93 | 46.5 min | 186k | 27.6M | **21/30** | 327 |
| **spec-r2** | $8.03 (hit the $8 cap) | 46.8 min | 228k | 41.9M | **21/30** | 351 |

The spec arms' 21/30 is not a defect: the ADR chose different names (namespace as a property) and moved test discovery
into the graph, and the acceptance script encodes the original prompt's contract. The behaviour checks below do not.

### Output quality, compiler truth (precision = correct / (correct + wrong) linked edges)

| Build | cJSON prec / recall | leveldb prec / recall | leveldb edges |
|---|---|---|---|
| prototype (mine) | 0.974 / 0.115 | 0.913 / 0.400 | 1,431 |
| plain-r1 | 0.982 / 0.321 | 0.918 / 0.572 | 2,028 |
| plain-r2 | 0.982 / 0.322 | 0.881 / 0.616 | 2,236 |
| devkb-r1 | 0.991 / 0.322 | 0.908 / 0.570 | 2,037 |
| devkb-r2 | 0.991 / 0.322 | 0.913 / 0.432 | 1,532 |
| devkb-r3 | 0.982 / 0.322 | 0.917 / 0.557 | 1,965 |
| devkb-r4 | 0.991 / 0.315 | 0.916 / 0.522 | 1,848 |
| spec-r1 | 0.983 / 0.313 | 0.904 / 0.508 | 2,107 |
| spec-r2 | 0.983 / 0.313 | 0.904 / 0.511 | 2,120 |

Edge quality is the same across arms within noise. **The spec did not make the call graph more accurate.**

### Behaviour checks (`behavior.py`, independent of naming; REQ = the owner's constraints, SPEC = the accepted decisions)

| Check | prototype | plain x2 | devkb x2 | devkb Bash-hook x2 | spec x2 |
|---|---|---|---|---|---|
| R1 pack lists a pointer-call caller | pass | pass | pass | pass | pass |
| R2 an ambiguous receiver is not guessed | pass | pass | pass (r2 links none) | pass | pass |
| R3 dependencies unchanged | pass | pass | pass | pass | pass |
| R4 limits stated in README | pass | pass | pass | pass | pass |
| **R5 pack never says Complete while a caller is unfollowable** | **fail** | **fail** | **fail** | **fail** | **pass** |
| D3 frameworks recorded per test case, ztest | fail | fail | fail | fail | pass |
| D4 a thrown message traces to its function | fail | fail | fail | fail | pass |
| D5 overloads carry a count | fail | fail | fail | fail | pass |

Total: REQ 4/5 for every unspecified build, **5/5 for both spec builds**; SPEC group 2/8 (prototype), 3-4/8 (plain, devkb),
**8/8** (spec). The honesty result (R5) is the owner's headline constraint, and only the specified builds meet it.

## 4. What the three arms show

- **Cost:** the spec arms cost 3-4x ($5.9-$8.0 against $1.8-$2.7) and took 2-3x the wall time. They built six tickets
  and 30+ more tests; the prompt for the other arms asked for less. Tokens scale the same way (cache reads 28-42M against
  4-8M). Cost per delivered behaviour check is closer than the raw ratio, but still higher.
- **Quality:** the call-graph accuracy is the same; what the spec bought is the **honest Incomplete flag, error
  extraction, framework labels and overload counts**, none of which an agent builds when the prompt does not ask.
- **devkb itself:** across all eight devkb-arm runs the agents made **0 MCP calls and 0 shell `devkb pack` calls**. Every
  difference between the plain and devkb arms is therefore run-to-run variation, as in the four earlier rounds.

## 5. Abnormalities found, investigated, and what changed

| # | Abnormality | Cause (verified) | Action |
|---|---|---|---|
| A1 | The pre-edit hook never fired | agents used `Edit`/`Write` on an existing file in 0 of 6 builds; they read with `cat`/`sed` and change files with Python scripts through **Bash** | hook extended to Bash (packs of up to two tracked files the command names, once per session); real-Claude test passed; 286 tests. Re-measured: delivered 8 files in a run, **agent still made no devkb call, cost and quality unchanged** |
| A2 | `pack refactor Store.add` answered "ambiguous" whenever two classes shared a method name (C++ and Python) | `_resolve` kept only the last dotted component | fixed with a qualified-suffix match, plus a test; a separate branch |
| A3 | Compiler truth first showed 0.70 precision | libclang had no system headers, so one function had a different USR per translation unit | truth rebuilt with the compiler's include path: 26-34% more edges, precision 0.88-0.98 |
| A4 | A result event per wake-up made costs and turns wrong | the CLI emits one per resumed turn | totals now from cumulative `modelUsage` and max `total_cost_usd` |
| A5 | My checker passed arms that lacked a feature | a fixture put the function name inside the message; a check called an API the spec arms had moved | fixtures and checks corrected, then re-scored |
| A6 | `make gate-0` missing in the clone | onboarding writes its Makefile stub only "if absent"; devkb has one | `make -f factory/Makefile gate-0` used; ODSF defect to fix |
| A7 | Gate 0 refused 3 stories | a cited evidence file outside the repo; one criterion neither a command nor Given/When/Then | two TL edits; BA should cite repo paths and write GWT |
| A8 | `DKB-006` filed as TASK | the BA's item lacked the user-story form; gate 0 skips tasks | noted; same defect class as the earlier pilot (#6) |
| A9 | ADR and original prompt disagree on names/APIs | the architecture persona made two choices the prompt did not | acceptance by prompt: 21/30; by behaviour: 8/8. The spec should state compatibility |
| A10 | BA run 1 asked for a devkb graph that did not exist yet | graph built after the job started | re-run with the graph: cheaper and cleaner |
| A11 | Orchestrated builds cannot use devkb's MCP tools | allowlist has no `mcp__*`; only a settings hook reaches them | builds in this evaluation used direct agent runs; ODSF change proposed |
| A12 | Edge precision about 10% wrong on leveldb in every build | unique-name and same-scope links to the wrong overload or receiver | open |

## 6. Manual interventions in the chain

Finalize the analysis (by design); fix a missing evidence path; reword one criterion; copy the evidence file into the
repository; run gate-0 through `-f factory/Makefile`; add `ai_policy` to the new project's config (the first attempt used a
wrong key and the router refused); re-run the analysis with the graph. The ODSF pilot of 2026-10-22 recorded 12.

## 7. Recommendations

1. **Take the spec's behaviours, not its cost.** The honest Incomplete flag (R5) is the one thing the owner asked for that
   no plain build delivers: merge `spec-r1` as the base and measure its recall problem (0.51 vs 0.57-0.62) separately.
2. **Improve edge quality where the compiler says it is lost:** constructor calls (+16% recall), typed receivers (+14%),
   and the 10% wrong edges. All three are measurable with `quality.py` against `truth_clang.py`.
3. **Make the agent use devkb, or stop claiming a benefit.** Eight runs, zero calls. The Bash hook now puts packs in
   front of the agent; the next test is a change-impact task (leveldb question) where the pack decides the answer, not a
   feature build where reading code dominates.
4. **Fix ODSF:** gate-0 for projects with their own Makefile (A6), an `mcp__*` allowance or a hook-based devkb path for
   orchestrated builds (A11), and BA stories that pass the ticket standard first time (A7, A8).
5. **Use BMAD alone for a repository this size.** Registering the project with the ODSF factory added a registry entry, a
   ticket store, a readiness gate and a landing tool; they cost more steps than they saved (items A6-A8 and the landing
   refusals: one branch for six tickets, a per-worktree BMAD install, a policy check on an unfilled result section). The
   BMAD personas produced the requirement analysis, specification and ADR on their own; the ODSF layer was removed
   afterwards and BMAD kept as a standalone install.
6. Keep the compiler truth in the benchmark: it found that the earlier "300/300" check was measuring the wrong thing.

## Files

`bench/cpp/truth_clang.py` (compiler truth, needs `pip install libclang` and `g++`), `bench/cpp/quality.py` (precision and recall
against that truth), `bench/cpp/behavior.py` (the behaviour checks). The decisions are in `docs/adr/ADR-DEVKB-008_c-cpp-support.md`.
