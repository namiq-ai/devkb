# devkb usage on the single-arm tickets of 0.2.15 (2026-11-22)

**What this is.** One agent (the author of the changes), one session, no comparison arm: the stage in which the milestone's tickets that need no benchmark were done in a chain (#396, #390, #391, #370, #358, #405, #368, #406, #119; #244 and #121 closed on measurements made earlier). Each ticket's interval was marked with `bench/audit/ticket_usage.py` (`mark start|end`) and the intervals read against devkb's telemetry (`.devkb/process-api-telemetry.jsonl`), the guardrail's decisions (`~/.claude/hooks/devkb-guardrail.log`) and the session transcript's tool calls (`bench/audit/toolmix.py` classes). Stage: 2026-11-22 16:25 to 18:17 local.
Reproduce: `python bench/audit/ticket_usage.py report --session d417ed39` (the marks are in `.devkb/ticket-usage-marks.jsonl`, local).

## Per ticket

| ticket | what was done | window | devkb queries (tools) | hook decisions / answered | session tool calls | devkb share of navigation |
|---|---|---|---|---|---|---|
| #396 | `uses` marks other-case definitions | 16:25 | 5 (pack 1, symbol 2, uses 2) | 1 / 0 | devkb 3, search 1, run 2 | 75% |
| #390 | shared name resolved in the searched files | 16:25-16:28 | 2 (pack 1, symbol 1) | 0 / 0 | devkb 1, search 1, read 2, run 5 | 25% |
| #391 | complete names of a several-name search answered | 16:28-16:42 | 0 | 3 / 0 | search 8, read 3, run 8 | 0% |
| #370 | release checklist step | 16:43 | 0 | 0 / 0 | read 1, run 2 | 0% |
| #358 | assessed, not changed | 16:43 | 0 | 0 / 0 | search 1, devkb 1 | 50% |
| #405 | Zephyr: one index per build | 16:43-17:20 (two spans) | 1 (symbol 1) | 2 / 0 | search 4, read 6, run 13 | 0% |
| #368 | thresholds recorded | 16:47-16:48 | 0 | 0 / 0 | search 2, run 1 | 0% |
| #406 | constructors: scorer and `new T;` | 17:36-18:17 | 1 (symbol 1) | 5 / 1 | devkb 1, search 6, read 10, run 24 | 6% |
| #119 | (same work as #406) | 17:40-17:49 | 0 | 1 / 0 | read 3, run 8 | 0% |

The intervals are the time between two marks, so they overlap in a few places (#406 and #119 were one piece of work; the replay behind #390 and #391 ran once, in #391's span) and a ticket's work before its first mark is not counted. The per-ticket counts are small enough to be read only as a pattern.

## The whole stage

| | |
|---|---|
| devkb queries | **11**: `symbol` 6, `uses` 3, `pack` 2 (no `callers`, `tests_for`, `outline`, `error`; no MCP tool calls) |
| tool calls in the session | run 73 (tests, scripts, benchmarks), search 27, read 27, devkb 7, other 6 |
| devkb share of navigation (devkb / devkb + search + read) | **11.5%** (7 of 61); the earlier periods of the same author's sessions were 2% to 8% (`devkb-usage-0.2.15-by-period.md`) |
| guardrail decisions in the session | 13: answered 1 (7.7%); passed through 12: `not-complete` 7, `intent:count` 2, `intent:unknown` 2, `intent:list-files` 1; `stale-graph` 0 |

## Reading it

1. **devkb was a minor part of how this work was navigated: 11 queries against 140 tool calls in the session (about one in thirteen).** Most of the stage was running things (73 run calls: the full suite four times, the replays, the Zephyr timings, the compiler truth) rather than finding code. The tickets were mostly changes in files the author already had open.
2. **`pack` before editing a file (this repository's rule) was followed twice**: `pack file devkb/read_tools.py` before #396 and a `pack refactor definition_answer` before #390. The other source files edited in the stage (`scripts/devkb_guardrail.py` for #391, `devkb/cpp_symbols.py`, `devkb/cpp_resolve.py`, `devkb/cpp_graph.py`, `bench/cpp/quality.py`) were edited without a pack of their own; `pack` was not used on them. This is a failure to follow the repository's rule, not a finding about the tool.
3. **The hook added little to this stage**: one answer in 13 decisions. Seven of the twelve pass-throughs were `not-complete` (a name several symbols share), which #390 and #391 now narrow for searches in files; the graph was not stale at any decision (the post-commit hook and a manual rebuild before the stage kept it at HEAD).
4. **No devkb answer in the stage was found wrong.** One observation from the work just before it is not resolved: during #409 a hook answer cited `scripts/devkb_guardrail.py:1350` and `:1382` where grep showed `:1351` and `:1385`, in a file with uncommitted edits. It was not reproduced (the working tree has moved on, and no log line was found for it), so no ticket was filed; the staleness check it points at was changed in #410.
5. **Where devkb did help, by the numbers recorded**: `symbol --source` gave the exact bodies of `render_uses`, `ReadTools.uses`, `definition_answer`, `shaped_answer` and `constructs_in` in one call each; the `pack refactor` for `definition_answer` said it had a single caller (**Complete**), which let #390 add a branch without searching for others. Neither is a measurement of saved time or tokens.

## What this does not show

- **No effect of devkb on the work's speed, cost or quality**: there is no arm without devkb. The two-arm benchmarks of the milestone are for #389, #386 and #313 only.
- **No per-ticket attribution beyond the interval.** A query is counted for the ticket whose interval it falls in; the telemetry does not record the ticket.
- **One agent, one session**, and the author of the tool; not a sample of how users work.
