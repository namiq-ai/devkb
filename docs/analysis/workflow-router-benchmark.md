# Workflow router: benchmark on four real tickets (2026-11-20/21)

**Question.** Does pushing the graph's answer at prompt time (`devkb hook prompt`, docs/specs/workflow-router.md) change cost,
turns or quality on real tickets? **Answer: not detectably.** The data cannot separate the router from noise, and in the cells
where it pushed something the pushed leads were mostly wrong.

## Design
Tickets #203, #118, #120 (C++ support) and #205 (a bug fix), each at the parent of its fix's merge commit, scored by the existing
hidden check `bench/policy/accept/<N>.py` and the full suite. Arms: `none` (no devkb), `rmain` (devkb and its guardrail, no router),
`router` (the same devkb commit plus the prompt hook; the only difference). Two forms: as filed, and with the ticket's location
withheld (#337's `POLICY_HIDE_START`). 3 reps per cell, Sonnet, `bench/policy/runs/` (local). Router arms: v2 (`5932278`).

## Results (n = 3 per cell; pass = hidden check and suite)

| cell | pass | cost $ | turns | context k | router |
|---|---|---|---|---|---|
| 118 none / rmain / router | 3/3, 3/3, 3/3 | .48, .36, .55 | 22, 18, 24 | 1187, 790, 1372 | located (nothing pushed) |
| 118 withheld: none / rmain / router | 3/3, 3/3, 3/3 | .43, .46, .44 | 22, 25, 24 | 1041, 1262, 1175 | navigate, 490 chars |
| 120 none / rmain / router | 3/3, 2/3, 2/3 | .64, .60, .79 | 26, 26, 30 | 1493, 1491, 1978 | navigate, 542 chars |
| 120 withheld: none / rmain / router | 3/3, 2/3, 3/3 | .66, .70, .68 | 26, 29, 30 | 1454, 1681, 1690 | navigate, 564 chars |
| 203 none / rmain / router | 3/3 each | .24, .19, .24 | 13, 14, 14 | 387, 434, 432 | located |
| 203 withheld | 3/3 each | .18, .20, .18 | 13, 16, 14 | 383, 493, 419 | ticket (empty) |
| 205 none / rmain / router | 2/3 each | .41, .33, .36 | 16, 13, 12 | 754, 598, 531 | located |
| 205 withheld | 3/3, 2/3, 2/3 | .28, .33, .37 | 11, 14, 14 | 472, 623, 670 | error (refused by the proof gate) |

*Corrected 2026-11-21 (errata 3): the four withheld `rmain` cells first held a wave of runs that was later discarded (devkb commits
436587e and 5932278, see errata 1); they are replaced by the runs at f3f9a49 that exist now. The `rmain` and `router` arms still
come from different waves (`rmain` as filed 436587e or 5932278, withheld f3f9a49; `router` 5932278), so differences between them
include a wave effect that errata 1 puts at about 3 turns.*

**Matched means over the four tickets, both forms, 24 runs per arm, from the runs on disk:** `none` 18.6 turns, $0.41, 896k context,
pass 23/24; `rmain` 19.5 turns, $0.40, 922k, 20/24; `router` 20.3 turns, $0.45, 1033k, 21/24. So the router is **+0.8 turns, +$0.05
(+13%) and +111k context (+12%) against `rmain`**, and `rmain` is +0.9 turns and -4% cost against `none`; none of it is distinguishable
from the design's noise floor (an A/A comparison moved 2.8 turns).

## What it shows
1. **No effect is detectable.** Where the router pushed nothing (`located`: #118, #203, #205 as filed) it still cost +9% to +51%
   against `rmain`; the same cell run twice differed by up to 35% (#203 router: $0.175 then $0.240, same behaviour). Cost gaps of that
   size are batch and run noise, so the +31% on #120 is not evidence against the router either. `none` against `rmain` is the
   guardrail's doing, and is also within that noise on three of four tickets.
2. **The ticket text decides, and tickets carry their location.** As filed, 3 of 4 tickets routed to `located` (bypass, by design).
   Withholding the location leaves nothing the graph can resolve (#203: only a spec ticket the benchmark graph lacks).
3. **When the router pushed, precision was low.** #120's bundle had three leads: `Repo.method_on` at `cpp_resolve.py:233` (a file the
   fix changed), a test function, and `add` in a TypeScript fixture. Fixed after the run (generic backticked words and
   test/fixture-only matches are skipped); not re-measured.
4. **No quality signal separates the arms.** The "#120 withheld, `rmain` 0/3" in the first version of this note belonged to the wave that
   was later discarded; the `rmain` runs on disk now pass 2/3 there. Pass rates over the matched runs are 23/24, 20/24 and 21/24
   (none, `rmain`, router); the one cell that stays lower for devkb arms is #205 withheld (see the live-batch note below).

## Problems found and fixed on the way
- A fixture path in a reproduction (`src/a.cpp L8-10`) bypassed the router; `file:line` now counts only for a tracked file.
- `SPEC-DKB-004` was read as ticket `DKB-004`; `L260-261` as a ticket key.
- **27 runs were invalid:** the account's usage limit ended them after one turn (`is_error`, "5-hour limit"): every #205 run and #120's
  withheld form. They are archived in `bench/policy/runs-archive/invalid-usage-limit/` and were re-run; the first summary of
  this work wrongly read their 0/3 as results.
- Some runs were flagged "contaminated" because I committed to the harness repository while a batch ran; the entries are my own commits
  and archive moves, never an agent's write. (The first version of this note said seven #118 runs; the flags on disk now are three
  `p118-nonehid` runs and three `p120-ctxhid` runs, so that count is withdrawn.)
- Router arms ran in a later batch than `rmain`/`none` (the harness wants one shuffled batch); that is the likely source of the
  larger-than-noise gaps in `located` cells.

## What would settle it
A shuffled batch of all arms together; at least 5 reps; tickets whose text names no file but does name code or an error; the v3
router (precision fix). Until then the router is unproven: it costs nothing when it has nothing to say, and has not been shown to
help when it does.

---

# Update (2026-11-21): root causes, fixes, and the batch after them

The first version of this note listed four suspected causes of low devkb use. Each was checked against the recorded runs
(`bench/policy/replay_queries.py` replays every recorded devkb query on the ticket's base graph, with no model runs).

| suspected cause | finding | action | measured |
|---|---|---|---|
| a wrong first match for an ambiguous name | **Confirmed.** 8 of the 13 off-target `symbol` answers were one query, `symbol resolve`: six exact matches, ordered by caller count, so the busiest file led whatever the ticket was about. The CLI is stateless, so "the file the agent just opened" does not exist; the ticket text is the usable signal. | `session_context`: the prompt hook records the task's words; `symbol` breaks ties by them (`devkb hook context` records only, pushes nothing). | replay: `symbol` top-1 on target 14/27 -> 22/27, no query worse. Both files the agent worked in now rank 1-2 (were 4+). The new top-1 is the `#include` resolver, not the macro one: the word "graph" in the ticket's boilerplate tipped it. Not tuned further (BENCHMARK.md). |
| guessed names return unrelated symbols | **Confirmed, not fixed.** `merge`, `overload` are real names the ticket never needed; no ranking can fix a name that does not exist. | none | 5 of 27 `symbol` queries |
| `pack` gives the worst answers | **Refuted.** The pack said "Incomplete: 17 calls could not be attributed". The agents' own `sed -n 5,14p` cut it. A verdict line at the top did not help `sed` ranges and moved the section out of one range. | change reverted | 6 of 7 `head`-style pipes kept the verdict even before |
| `outline` is net neutral | **Refuted.** Devkb arms pull fewer characters of locating output (grep, read and devkb results) into context: **-15%** (49.6k against 58.6k per run, 90% interval [-11.5k, -6.4k]) for `rmain` against `none`, -7% to -26% on every ticket; -11% for the router. (First figure: -18%, computed with the wave that was later discarded.) | none | |

Also found: agents pipe devkb output through `head`/`sed`/`tail`/`grep` in 57 of 85 navigation calls.

## Live batch: `rmain` against `ctx` (the same devkb commit f3f9a49; the only difference is the silent hook), location withheld, 3 reps

36 runs, none invalid or cut off. 3 are flagged "contaminated", and every flag lists only my own archive moves. The task record
was present in all 18 `ctx` checkouts and in none of the `rmain` ones. 118, 120, 203, 205 are the tickets the ranking was
derived from; 286 and 287 were not seen before.

| | rmain | ctx | difference (90% interval) |
|---|---|---|---|
| turns (all 6 tickets, n = 18 each) | 20.6 | 17.7 | -2.8 (-4.9, -0.8) |
| cost $ | 0.38 | 0.34 | -0.04 (-0.07, -0.01) |
| context, k tokens | 909 | 764 | -145 (-249, -43) |
| devkb navigation calls | 1.06 | 1.11 | +0.06 (-0.11, +0.22) |
| search / read-type calls (Bash grep, rg, find, ls and the Grep tool / the Read tool plus Bash sed, cat, head) | 6.6 / 4.3 | 5.9 / 4.1 | -0.7 / -0.2 (both span zero); the Read tool alone is 1.2 / 1.8 per run |
| hidden check and suite | 16/18 | 15/18 | #205: 2/3 against 1/3; #120 2/3 each |
| held out (286, 287; n = 6 each) | turns 19.5, $0.28 | 17.3, $0.26 | -2.2 (-7.2, +2.2); 6/6 and 6/6 |

Intervals: 90%, a bootstrap that resamples runs within each ticket and arm and weights the six tickets equally (corrected on
2026-11-21; this note first gave unpaired intervals without naming the method, which put zero inside them). **Reading.** Within
this batch, `ctx` is lower on turns, cost and context under that test. The result is not robust, for two reasons stated in the
errata: the same arm differed by 3.4 turns between two waves, and the 118 and 120 arms were run 35-45 minutes apart. The hook
adds no turns (it pushes nothing). Live `symbol` calls are rare: 9 for `rmain` and 11 for `ctx` over 18 runs each (9 of the
`ctx` calls returned a match; top-1 on target 3 of 9 against 2 of 9), so even a perfect ranking can touch few calls. The per-cell
swings (#118: 25.0 against 17.3 turns) are larger than those few queries can explain.

**What it supports.** The ranking is correct on the recorded queries and costs nothing at run time, so it is safe to ship. It
does not by itself change what agents do; the bound is how seldom they ask.

---

# Update 2 (2026-11-21): the guardrail fixes, replayed offline

*Superseded in its numbers by Errata 2 and 3 below: 72 devkb-arm runs (not 48), 42 of 301 decisions answered (not 54 of 381), 690 searches, +14 partial answers (not +21), and an answered share that would rise from 14% to about 19-23%, not a measured gain.*

Question: would answering more of the searches agents already run (the guardrail) change much? Replayed on the 48 devkb-arm
runs of tickets 118, 120, 203, 205, 286, 287 (394 grep/rg searches), no model runs: `bench/policy/hook_replay.py` (the
guardrail's decisions on each run's calls, on the ticket's base tree) and `bench/policy/stale_replay.py` (the staleness rule).

| | result |
|---|---|
| the guardrail today, replayed | 54 of 381 decisions answered (14%; the live runs gave 9%): 40 span hints (about 50 characters) and 14 `alongside`; **no `substitute` at all**, so no grep was replaced by a graph answer in these runs |
| withheld, before the first edit (269 decisions) | not complete 116, duplicate of an earlier answer 70, file lists 16 |
| fix 1, a rebuild when the graph is stale | **not viable**: a full `devkb build` takes 12-13 s on these checkouts (the hook's limit is 20 s) and would repeat after every edit |
| fix 1', stale only when a file the names depend on changed | 275 of 394 searches (70%) came before the run's first edit, so staleness could not have withheld them. Of 42 searches after it that name a graph symbol, 15 would be answered and 27 not (the agent had edited the files it was searching): **15 of 394, under 4%** |
| fix 2, an `alongside` answer for the names that are Complete, with the others listed | answered 54 -> 75 (14% -> 19%); +127 characters per run (about 32 tokens). The 21 new answers are beside grep, so they replace nothing; many are for ordinary words that happen to be symbols (`macro`, `kind`, `build`, `calls`). In 0 of the 21 did the agent's next call look the same names up again. Value not demonstrated; the change was not kept (patch: not in the repository) |

**Reading.** Even with both fixes the answered share would rise from 14% to about 23%, and the added answers are hints beside
grep, not replacements. The searches agents run are mostly one-file reads (`in-file`, `read-body`), where grep prints the lines
the answer would. The guardrail's ceiling on tickets of this kind is therefore low, and the answered share is not the number
that would move turns or tokens.


---

# Errata (2026-11-21), from an independent audit of this note

The headline numbers reproduce from `score.json`. What was wrong or missing:

1. **The interval method was not named, and the one used was too wide.** Unpaired, the turns interval was (-6.6, +1.0). Resampling
   runs within each ticket cell gives (-4.9, -0.8), cost (-0.067, -0.010), context (-249k, -43k). A paired bootstrap over the six
   per-ticket differences (`release_table.bootstrap`) gives about (-4.8, -0.9). The earlier sentence "none is distinguishable
   from noise" is withdrawn; it depended on the choice.
2. **The result is not robust to a wave effect.** I discarded 12 earlier `rmainhid` runs (devkb commits 436587e and 5932278, so they
   could not be compared). On tickets 118, 120, 203 and 205 they averaged 17.7 turns against 21.1 for the replacements: the same
   arm moved +3.4 turns between waves, as much as the effect claimed. Pooling them gives -1.7 turns (-3.7, +0.25). The
   118 and 120 `rmain` runs finished 35-45 minutes after the matching `ctx` runs, so those two tickets were not interleaved.
3. **Column labels.** "grep" is `grep`, `rg`, `find`, `ls` and the Grep and Glob tools; "read" is the Read tool plus Bash `sed`,
   `cat`, `head`, `tail`, `wc` and `git diff`/`log`. The Read tool alone is 1.2 (`rmain`) and 1.8 (`ctx`) per run.
4. **Symbol queries:** 9 for `rmain`, 11 for `ctx` (9 returned a match), not "9 per arm".
5. **Contaminated runs.** `release_table.py` drops runs flagged `contaminated` from every mean; this note kept three `p120-ctxhid`
   runs whose flags list only my own moves of `runs-archive/` files. The harness now ignores `runs-archive/` (see the harness
   fixes), so the tool and this note agree.
6. **Refetch.** The metric counted generic words (`cpp`, `resolve`, `constant`) as targets and counted an `outline` followed by a
   ranged Read, which is by design. Corrected (`storybench.refetch`; targets are distinctive names and files, the outline case is
   counted apart): **14 of 76 devkb queries (18%) were re-fetched**, not 33 of 83 (40%). By arm: `router` 7 of 21 (33%), `rmain`
   4 of 16 (25%), `routerhid` 2 of 11, `ctxhid` 1 of 14, `rmainhid` 0 of 14; 19 further queries were an outline followed by the read it
   points to. The 64% for the router arm quoted in earlier notes was the old metric.


---

# Errata 2 (2026-11-21), from an independent audit of the replay tools, and what I checked myself

This supersedes numbers above. Each correction names the script that now produces the figure.

1. **The live `ctx` arm never ran the ranking.** I checked that the task record existed in the `ctx` checkouts, never that anything
   read it. The agent's own `devkb` is the checkout's `.venv/bin/devkb`, which is the ticket's base-commit code: the checkout has no
   `_task_overlap` and no `session_context.py`, and in all three #118 `ctx` runs the agent's `symbol resolve` printed
   `project_context.py` first, the old order. So the batch compared `rmain` with `rmain` plus a hook whose output nothing used: an
   **A/A comparison**. The -2.8 turns (-$0.04, -145k context) between two identical treatments, "significant" under the
   within-ticket resampling, is the noise floor of this design (a wave effect and run-to-run spread the resampling does not see),
   about 3 turns or 15% in either direction. Every statement above that the live batch favoured the ranking, and the "hook adds no
   turns" check, is withdrawn: the live data say nothing about the ranking. A live test needs the agent's `devkb` to be the arm's code;
   that conflicts with tickets that edit devkb itself (the agent self-tests its own build), so the ranking is judged by replay only.
2. **The ranking replay is one query.** The "14/27 to 22/27" (and the recount 14/32 to 25/32) counted `symbol resolve` on #118 eleven
   times. Per distinct query the four tickets give 8 queries: top-1 file on target 3 to 4 of 8; at function level (a definition the run
   actually changed) 1 of 8 before and after. The new top-1, `_Includers.resolve` in `cpp_graph.py` L35-45, was not touched by any
   agent; the function they needed, `cpp_resolve.py resolve`, is rank 2. On the held-out tickets 286 and 287 (4 distinct queries) nothing
   changes at either level (`replay_queries.py`, `--context`). **The ranking is unproven and no longer installed by default.**
3. **Inline pack coverage is 1.2 calls per run, not 2.5** (`inline_replay.py`): 91 of the first 144 "covered reads" were re-reads of a
   file already opened. Now 547 navigation calls in 72 runs (7.6 per run), 83 covered: 39 reads of a file a pack names but the agent
   had not opened, 44 greps. The inline idea fails its gate by a wider margin.
4. **Guardrail replay: 42 of 301 decisions answered (14.0%), not 54 of 381.** A glob and a directory had both matched the `ctx` runs, so
   80 decisions were counted twice (`hook_replay.py` now lists each stream once). 31 span hints and 11 `alongside`. Before the run's first
   edit, the figure comparable with the live guardrail (which withholds a stale graph): 18 of 209 (8.6%), against the live 9%. The replay
   and the live hook agree. 24 of the 42 answers come after the first edit, where the live rule would withhold them.
5. **Partial answers: +14 answers (42 to 56; 14.0% to 18.6%), not +21,** at about 20 tokens per run (re-run on the de-duplicated runs).
6. **Staleness: 690 searches, 521 (75%) before the first edit, 60 after it that name a graph symbol, and 6 answerable under a name-scoped
   rule** (6 of 690, 0.9%; not 15 of 394). The first count skipped unquoted patterns (355 of 734 shell greps) and saw only Edit and Write as edits;
   `searches.py` parses every grep and counts a shell write (`sed -i`, a heredoc, a redirect) as an edit (`stale_replay.py`).
7. **Which greps the graph could answer: 29%, not 47%** (`nav_habits.py`, 751 patterns, one classification, shares sum to 100%):
   distinctive graph symbols 28.8%; plain words that are also a symbol (`macro`, `names`, `variant`) 34.9%; names the graph does not define
   22.9%; text and regex 13.4%. The earlier 47% included the plain words, which are symbols by accident.
8. **`| head -N` on devkb output:** 68 piped navigation commands; **41 (60%) provably cut nothing** (the whole result was shorter than N);
   25 may have been cut and cannot be attributed in a chain. The earlier "44 of 54, 81%" did not reproduce (`nav_habits.py`).
9. **Not wrong, checked:** replay fidelity (the replay's old-order `symbol` output equals the live tool results exactly), the
   reconstruction of the hidden-location prompts (the same 174, 147 and 181 words the live runs recorded), `rel()` paths, and the guardrail
   replay against the live hook (point 4).


---

# Errata 3 (2026-11-21), from an independent audit of the documents and a review of PR #401

1. **Router effect: +0.8 turns and +13% cost against `rmain`, not +2.6 turns.** The +2.6 compared the router with the 12 discarded
   `pre-ctx-batch` runs (17.7 turns). On the runs on disk, 24 per arm over the four tickets: `none` 18.6 turns, $0.41, 896k context,
   pass 23/24; `rmain` 19.5, $0.40, 922k, 20/24; `router` 20.3, $0.45, 1033k, 21/24. The conclusion (no effect distinguishable from the
   design's noise floor) stands, and the router looks slightly worse than first reported. The first Results table's four withheld `rmain`
   cells and "What it shows" item 4 (`rmain` 0/3 on #120 withheld) belonged to the discarded wave and are replaced above.
2. **Locating characters: -15%, not -18%** (49.6k against 58.6k per run for `rmain` against `none`; 90% interval [-11.5k, -6.4k]; -7% to
   -26% per ticket), computed on the runs on disk.
3. **Replay figures after the final search parser** (the parser was rewritten after the first audit and now reads `git grep`, wrappers,
   option values, repeated `-e`, heredocs): 690 searches, 521 before the first edit, 60 after it naming a graph symbol, 6 answerable;
   751 patterns, 28.8% distinctive symbols; 547 navigation calls, 1.2 covered per run, 2441 tokens of packs per run if every opened file
   were answered inline. `head` is unchanged: 41 of 68 piped commands provably cut nothing.
4. **QB1 health.** "Every test file ran, none failed or was skipped" was wrong: `test_csharp_symbols.py` has a failing test at all eight
   snapshots, two other files fail at two each, and 7 tests are skipped at 7 snapshots (see `qb1-baseline.md`). All five held-out snapshots
   have a failing test, not two. And "a real, replicated gain" overstated QB1: after the review fixes the held-out gain of the shipped pack
   over the original is **+0.04 (0.00 to +0.08)**, its lead over import +0.21 and over grep +0.11, so the 15-point gate is not met held-out.
5. **Test count.** The PR said the suite passed with 1226 tests; on the branch after the review fixes it is 1233 collected, 1231 passed, 2
   skipped (the earlier plan text said 1216).
6. **Small figures.** Devkb navigation calls `rmain` 1.06 against `ctx` 1.11: +0.06 (-0.11, +0.22), not (-0.33, +0.50). The refetch
   denominators are 76 queries by the script and 73 by an independent recount (the `refetch` field is stored in only part of the
   `score.json` files; the table is computed from the streams). "9 and 11 symbol queries" counts calls that returned a match; a plain
   count of `devkb symbol` commands in the streams gives 12 and 13. The stale-graph "6 answerable" was 7 with the earlier parser.
7. **Contamination flags.** The "seven #118 runs" cannot be reproduced; three `p118-nonehid` and three `p120-ctxhid` runs carry flags
   today, all my own commits or archive moves.
8. **Stale statements in other documents** (the plan still said the silent hook was the `init` default, the graph-defect tickets were not
   posted, the spec called the router installed by the plugin, `guardrail-combine.md` quoted the first guardrail numbers) are corrected
   in place; `quality-benchmarks.md` now says what was built, and `qb2-baseline.md` no longer says the graph has `LOGS` edges here.
