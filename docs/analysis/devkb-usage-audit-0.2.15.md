# How devkb was used in 0.2.15: an audit (2026-11-22)

> **Correction (2026-11-22):** section 3's window started at 20:00 on 11-20, but the v0.2.14 tag is at 01:59 that day, so it left out 18 hours. Over the full window `stale-graph` is 465 of 1,516 decisions (31%), 33% of pass-throughs (not 46%), and the answered share is 7.2% overall. The corrected figures, grouped by the fixes that change what an agent sees, are in `devkb-usage-0.2.15-by-period.md`; where the two differ, that one is right.

**Scope.** Everything recorded since the v0.2.14 tag (2026-11-20 evening) to 2026-11-22: the two working sessions that built 0.2.15, the guardrail log for every Claude Code session on this machine
(working and benchmark), devkb's own telemetry, the graph-miss log, and the benchmark arms of 0.2.15. The numbers are from the logs listed under Sources; each can be recomputed.
**Not covered:** the audit and fix sub-agents of 0.2.14 (see `bench/audit/toolmix-results.md`); any use outside this machine.

## 1. The working sessions: devkb is a small share of navigation

`bench/audit/toolmix.py` on the transcripts (class definitions in the script; a quoted `devkb ...` in a commit message is not a query, #309):

| session | devkb queries | search calls | read calls | run calls (tests, scripts) | devkb share of navigation calls | of navigation text |
|---|---|---|---|---|---|---|
| 0.2.14 release (reference, ended 2026-11-20) | 34 | 267 | 162 | 334 | 6% | 5% |
| 0.2.15 C/C++ extractor tickets | 38 | 362 | 199 | 472 | 5% | 3% |
| 0.2.15 milestone-4 chain (this one) | 26 | 330 | 231 | 552 | 4% | 3% |

- The devkb MCP tools were called 3 times in the first session and 15 times in the second (symbol 12, outline 2, pack 1, uses 1); the rest was the CLI.
- **Reading it:** in the sessions that built a tool whose rule 1 is "ask devkb first", devkb answered 4-5% of the navigation calls and 3% of the text. The repository's telemetry shows `pack` 110 times in total (section 2); whether each was run before the first edit of a file was not checked.
  The author of this audit is the agent in these sessions; this is a finding about that agent, not an outside observation.
- Ticket-level usage on the 0.2.15 tickets is not recorded per ticket (no ticket id is logged with a query); the per-ticket checklist steps 2 and 3 were skipped for most tickets (see the Execution-result comments).

## 2. devkb's own telemetry (`.devkb/process-api-telemetry.jsonl`, this checkout)

175 queries from 2026-11-15 to 2026-11-22: `pack` 110, `symbol` 43, `tests_for` 10, `callers` 4, `uses` 3, `outline` 3, `tests_to_run` 2; 173 ok, median 33 ms. By day: 11-20 46, 11-21 118, 11-22 2.
It does not record who asked or for which ticket, so it cannot be split by session.

## 3. The guardrail's decisions since v0.2.14 (`~/.claude/hooks/devkb-guardrail.log`)

1,207 decisions in 223 sessions (2 working, 221 benchmark runs):

| | decisions | answered (`alongside`, `substitute`, `span-hint`, `read-answer`) | share |
|---|---|---|---|
| working sessions | 156 | 7 | 4.5% |
| benchmark runs | 1,051 | 49 | 4.7% |

- Pass-through reasons (928 decisions): **`stale-graph` 427 (46% of pass-throughs, 35% of all decisions)**, `not-complete` 243, `duplicate:read-body` 72, `intent:unknown` 49, `intent:list-files` 27, `duplicate:call-sites` 25, `duplicate:in-file` 25, `intent:count` 14. The reminder was printed once per session (223).
- **`stale-graph` is the largest single reason.** It is by design (#273: a graph that has not seen the searched files' current code gives wrong line numbers), and it concentrates in `in-file` (178) and `read-body` (133) searches of files the agent has just edited. 398 of the 427 are in benchmark runs, 29 in the working sessions (19% of their decisions).
  The #367 replay (`docs/analysis/hook-answer-rate-367.md`) searches the run's base and so cannot see this: its 7% to 10% answered rate on code-name searches is an upper bound for live runs. A lever, not yet a ticket: rebuild the changed files' part of the graph when the hook finds a stale scope.

## 4. The graph-miss log

`devkb misses` (this repository): 5 groups, all reviewed by hand here: `github` (cannot-resolve, a word search), `version` (a word), `post_feedback` (incomplete), `test_a_name_that_is_both_a_macro` (incomplete: a test name that is also a macro name), `main` (no-match, a word). **None is a graph defect to file;** the two `incomplete` ones are the graph saying it cannot follow every call.
30 earlier lines are already in `.devkb/graph-misses-reviewed.jsonl`. The log covers this repository only; the benchmark runs' checkouts keep their own logs (not collected here).

## 5. Agents under benchmark (0.2.15)

| benchmark | arms | runs | agents that ran devkb at all | result |
|---|---|---|---|---|
| yaml-cpp, 6 C++ bug fixes (`docs/analysis/cpp-yaml-benchmark.md`) | none / orig (main) / ship (PR #401) | 90 | none 0%, orig 10%, ship 47% (0.5 navigation calls a run, `pack` 2 times in 30) | 30/30 pass in every arm; no efficiency difference (cost $0.10 / 0.11 / 0.10) |
| #337 location withheld (`why-agents-do-not-query-devkb.md`, #385) | `none` / `main` and the hidden-location forms | see ticket | see ticket | the deciding experiment for "use when it matters" |
| PR review harness, #270 and #407 (`bench/review/results.jsonl`) | with / without devkb | 4 reviews | **0 devkb queries in all four**, though the devkb arm's prompt carried the packs | #407: 3 low defects found, no overlap between arms |

## 6. What this says

1. **devkb was not the main way anyone, human-directed agent or benchmark agent, navigated in 0.2.15.** 3-5% of navigation calls in working sessions, 0-47% of runs in the yaml-cpp arms, 0 of 4 reviews. This agrees with #381's finding that agents given line numbers read the file.
2. **What reached agents without being asked is the hook, and it answers about 1 search in 21** (4.5-4.7%), mostly held back because the searched file changed (stale graph), the name is shared (`not-complete`, #390), or grep prints the same lines.
3. **No devkb answer in this window was found wrong.** The audit did not re-check each of the 56 answers against source; it checked the 3 review findings (one downgraded). A wrong-answer audit of the hook's answers is not done.
4. The 0.2.15 measurements say what devkb changes in the *graph* (C/C++ edge recall, build time, release table) far better than what it changes in an *agent's* work, where the effect is not shown either way at these run counts (#368).

## Sources and how to recompute
- Transcripts: `~/.claude/projects/-home-namiq-orchestra-ip-devkb/{42e9d8fb,acc99be4,d417ed39}*.jsonl`; `python bench/audit/toolmix.py LABEL=FILE ...`.
- Guardrail log: filter `t >= 2026-11-20T20`, group by `action`, `reason`, `session`; "working" = the first two sessions above, the rest benchmark runs.
- Telemetry: `.devkb/process-api-telemetry.jsonl` (`t` is epoch seconds). Misses: `devkb misses --project .`.
- Benchmarks: `docs/analysis/cpp-yaml-benchmark.md`, `bench/review/results.jsonl`.
