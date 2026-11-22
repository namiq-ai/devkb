# devkb usage while building 0.2.15, before and after the fixes that change what an agent sees (2026-11-22)

**Window.** From the v0.2.14 tag (2026-11-20 01:59 local, -0600) to 2026-11-22 16:00. **This replaces the window of `devkb-usage-audit-0.2.15.md`**, which started at 20:00 on 11-20 and so left out about 18 hours of 0.2.15 work; its totals are corrected below.
Reproduce: `python bench/audit/usage_by_period.py` (guard log `~/.claude/hooks/devkb-guardrail.log`, `.devkb/process-api-telemetry.jsonl`, the working sessions' transcripts).

## 1. The periods: cut at the fixes an agent can see

| Period | From (merge time) | The fix that starts it | What changes for an agent |
|---|---|---|---|
| **P1** 0.2.14 as released | 11-20 02:00 | (the v0.2.14 tag) | The 0.2.14 hook and reminder; `symbol` lists matches in lower case. |
| **P2** | 11-20 12:35 | **#375** (#378) | The reminder names a devkb command that runs in this checkout; teach lines on duplicates are off by default. |
| **P3** | 11-20 19:38 | **#369** (#397) | Benchmark prompts say how to run commands, so the permission checker stops refusing devkb commands (0.2.13's 35 attempts were all refused). Before this, a benchmark could not see an agent use devkb. |
| **P4** | 11-21 17:28 | **#401** (#401's pack changes, router off by default, quality benchmarks QB1-QB4) | `pack` lists tests that mention a function; `pack error` precision (#399) and tuple-unpack attribution (#400) follow at 20:11. |
| **P5** | 11-22 15:46 | **#408** and **#410** | A search piped into a bare `head` gets its answer; a search is answered when no changed file mentions its name. Almost no data yet. |

Also merged inside these periods, listed for the record, not used as cuts because their effect on an agent is small or cannot be separated: #372 (case order of `symbol`, 11-20 02:21), #382 (alias and `runpy` dependents in `pack file`, 11-20 17:35), #337 (hidden-location benchmark arms, 11-20 16:08), #383 (`--allow-foreign-checkout`, 17:27). The 0.2.15 chain's guardrail and read-tool changes (#282, #284, #285, #288, #293, #317, #358) were developed on 11-21 and 11-22 and merged together at 11-22 14:22 (#407); in the working sessions the checkout's hook script is what ran, so they were live there from the day they were edited, but in benchmark runs only from the arm's pinned commit.

## 2. Working sessions (the agent building 0.2.15)

Guard log, searches the hook decided on (reminders excluded), working sessions only:

| Period | Decisions | Answered | Answered share | `stale-graph` | `not-complete` | `duplicate:*` |
|---|---|---|---|---|---|---|
| P1 | 35 | 3 | 8.6% | 1 | 24 | 5 |
| P2 | 105 | 3 | 2.9% | 19 | 51 | 19 |
| P3 | 71 | 1 | 1.4% | 11 | 41 | 7 |
| P4 | 89 | 7 | 7.9% | 18 | 24 | 13 |
| P5 | 0 | 0 | | 0 | 0 | 0 |
| **all** | **300** | **14** | **4.7%** | **49 (16%)** | **140 (47%)** | **44 (15%)** |

Tool mix of the working sessions' transcripts (`bench/audit/toolmix.py` classes), calls per period:

| Period | devkb CLI | devkb MCP | search | read | run | devkb share of navigation (CLI) |
|---|---|---|---|---|---|---|
| P1 | 1 | 0 | 27 | 26 | 60 | 1.9% |
| P2 | 19 | 0 | 168 | 83 | 212 | 7.0% |
| P3 | 14 | 2 | 170 | 91 | 216 | 5.1% |
| P4 | 16 | 17 | 215 | 148 | 348 | 4.2% (8.3% with MCP) |

devkb's own telemetry (this checkout; no session or ticket recorded): P3 56 queries (pack 26, symbol 18, tests_for 10), P4 104 (**pack 82**, symbol 19), P5 1. P1 and P2 have no telemetry rows at all (the log's earlier rows are from 11-15 and 11-19).

**Reading it.** The share of navigation that went through devkb stayed between 2% and 7% of the calls in every period (8% with the MCP tools in P4). It rose in P2 (7.0%), but one agent in one session cannot show a cause, and this audit does not claim one. The telemetry's large P4 `pack` count (82) is not explained by this data: the log does not say who asked or why, and it does not show up as more answers from the hook, because a hook answer and a deliberate `pack` are different things.

## 3. Benchmark agents (each batch is its own experiment)

Guard log, benchmark sessions only. **Caution:** a benchmark arm runs the hook code pinned to its commit, not the code of the day, so a period's row describes the batches run in it, not the fix that opened it.

| Period | Sessions | Decisions | Answered | Answered share | `stale-graph` | `not-complete` | `duplicate:*` |
|---|---|---|---|---|---|---|---|
| P1 | 52 | 116 | 22 | 19.0% | 5 | 43 | 22 |
| P2 | 89 | 221 | 18 | 8.1% | 11 | 136 | 27 |
| P3 | 157 | 590 | 42 | 7.1% | **233** | 151 | 95 |
| P4 | 66 | 265 | 8 | 3.0% | **167** | 47 | 17 |
| P5 | 6 | 24 | 5 | 20.8% | 0 | 13 | 2 |
| **all** | 370 | 1,216 | 95 | 7.8% | 416 (34%) | 390 (32%) | 163 (13%) |

**What the batches say about agents using devkb**, by period (numbers from each ticket's Execution result and the analysis notes):

| Period | Batch | Runs | Agents that ran devkb to navigate | Source |
|---|---|---|---|---|
| P1 | #375 teach line, 3 arms | 54 | 0 queries; the teach line was seen 17 times, 0 followed; +12.6% cost | `docs/analysis/why-agents-do-not-query-devkb.md` |
| P1 | 81 interviews of the agents | 81 | "the ticket gives line numbers" is the strongest reason; 6 of 63 asked said habit | same |
| P3 | #337, location withheld (4 tickets, 3 reps) | 48 | `main`: 5 of 12 runs (all on two tickets); `mainhid`: 2 of 12; `none`: 0 of 12 | #337's Execution result, #385 |
| P3 | #366 user-policy batches | | no agent used devkb to navigate (closing comment of #366) | #366 |
| P4 | yaml-cpp, 6 bug fixes | 90 | `none` 0%, `orig` 10%, `ship` 47% of runs; `pack` 2 times in 30; 30/30 pass in every arm; cost $0.10/0.11/0.10 | `docs/analysis/cpp-yaml-benchmark.md` |
| P4-P5 | two-way PR reviews (#270, #407, #408, #410) | 8 | **0 queries**, though the devkb arm's prompt carried the packs | `bench/review/results.jsonl` |

**Reading it.**
1. **Before #369 the measurement was blind, after it the answer is "rarely".** In 0.2.13 agents tried devkb and the benchmark refused all 35 attempts; after #369 agents are allowed to run it, and in P3 to P4 they do so in 0 to 47% of runs depending on the ticket and arm. Location withheld (#337) raised nothing: the one effect that points the right way is `main` against `mainhid` (5 against 2), so giving the location did not stop agents querying, it changed which tickets they queried on. n=3 per cell: a pointer, not a result.
2. **`stale-graph` becomes the hook's largest reason from P3 on** (233 of 590 benchmark decisions in P3, 167 of 265 in P4) because the benchmark agents edit the checkout while the graph is at the base. In the working sessions it is 16% of decisions. This is what #409 and #410 address; P5 has too little data (24 decisions) to show it; the clean live run is in progress (#409).
3. **The hook answered 7.8% of benchmark decisions and 4.7% of working-session decisions over the whole window.** Its answered share fell from 19% (P1) to 3% (P4) in the benchmark rows; this data does not say whether that is the hook or the batches (different tickets, different hook versions, a graph that was stale more often in P3 and P4). The comparison needs the same tickets on both hook versions, which only the #409 live run does.

## 4. What this audit corrects

- `devkb-usage-audit-0.2.15.md` and #409/#411 quoted `stale-graph` as 46% of pass-throughs (427 of 928) and 35% of decisions, for a window that started 18 hours late. For the full window it is **465 of 1,516 decisions (31%) and 33% of the 1,407 pass-throughs**, still the largest single reason in the benchmark rows (34%) and third in the working sessions (16%, after `not-complete` 47% and `duplicate` 15%). The conclusion stands, the figures change.
- The same document counted 1,207 decisions with the 223 reminders included; this one excludes them.

## 5. What it does not show

- **No effect of a fix on an agent's results.** A period is a calendar slice of one author's work and a different set of batches; the fixes are not randomised. The only controlled comparison in the window is a batch's arms (section 3).
- **No per-ticket usage.** Queries carry no ticket id; the 0.2.15 tickets cannot be ranked by how much devkb they used.
- **Whether the hook's answers were right** was not re-checked for the 109 it gave; the reviews found no wrong answer in the 8 reviews.
- **P5** is a few hours; its guard rows are benchmark probes only.

## 6. Follow-ups

#409 (live `stale-graph` share, running from a clean worktree), #390 and #391 (the `not-complete` group, 47% of working-session decisions), #411 (incremental graph update, 0.2.16), #368 (the thresholds that decide what a batch can claim).
