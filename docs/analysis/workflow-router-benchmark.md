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
| 118 withheld: none / rmain / router | 3/3, 3/3, 3/3 | .43, .44, .44 | 22, 21, 24 | 1041, 1092, 1175 | navigate, 490 chars |
| 120 none / rmain / router | 3/3, 2/3, 2/3 | .64, .60, .79 | 26, 26, 30 | 1493, 1491, 1978 | navigate, 542 chars |
| 120 withheld: none / rmain / router | 3/3, 0/3, 3/3 | .66, .46, .68 | 26, 24, 30 | 1454, 1091, 1690 | navigate, 564 chars |
| 203 none / rmain / router | 3/3 each | .24, .19, .24 | 13, 14, 14 | 387, 434, 432 | located |
| 203 withheld | 3/3 each | .18, .17, .18 | 13, 13, 14 | 383, 401, 419 | ticket (empty) |
| 205 none / rmain / router | 2/3 each | .41, .33, .36 | 16, 13, 12 | 754, 598, 531 | located |
| 205 withheld | 3/3, 2/3, 2/3 | .28, .34, .37 | 11, 12, 14 | 472, 567, 670 | error (refused by the proof gate) |

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
4. **One quality signal, not trustworthy:** #120 withheld, `rmain` 0/3 against `none` and `router` 3/3. Three runs; no cause found.

## Problems found and fixed on the way
- A fixture path in a reproduction (`src/a.cpp L8-10`) bypassed the router; `file:line` now counts only for a tracked file.
- `SPEC-DKB-004` was read as ticket `DKB-004`; `L260-261` as a ticket key.
- **27 runs were invalid:** the account's usage limit ended them after one turn (`is_error`, "5-hour limit"): every #205 run and #120's
  withheld form. They are archived in `bench/policy/runs-archive/invalid-usage-limit/` and were re-run; the first summary of
  this work wrongly read their 0/3 as results.
- Seven #118 withheld runs are flagged "contaminated": the only entries are two router commits made during the batch.
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
| `outline` is net neutral | **Refuted.** Devkb arms pull ~10k fewer characters of locating output per run (-18%, all four tickets, -11% to -31%; 90% interval [-21k, +0.1k]). | none | |

Also found: agents pipe devkb output through `head`/`sed`/`tail`/`grep` in 57 of 85 navigation calls.

## Live batch: `rmain` against `ctx` (the same devkb commit f3f9a49; the only difference is the silent hook), location withheld, 3 reps

36 runs, none invalid or cut off. 3 are flagged "contaminated", and every flag lists only my own archive moves. The task record
was present in all 18 `ctx` checkouts and in none of the `rmain` ones. 118, 120, 203, 205 are the tickets the ranking was
derived from; 286 and 287 were not seen before.

| | rmain | ctx | difference (90% interval) |
|---|---|---|---|
| turns (all 6 tickets, n = 18 each) | 20.6 | 17.7 | -2.8 (-6.6, +1.0) |
| cost $ | 0.38 | 0.34 | -0.04 (-0.13, +0.06) |
| context, k tokens | 909 | 764 | -145 (-400, +117) |
| devkb navigation calls | 1.06 | 1.11 | +0.06 (-0.33, +0.50) |
| grep / Read | 6.6 / 4.3 | 5.9 / 4.1 | -0.7 / -0.2 (both span zero) |
| hidden check and suite | 16/18 | 15/18 | #205: 2/3 against 1/3; #120 2/3 each |
| held out (286, 287; n = 6 each) | turns 19.5, $0.28 | 17.3, $0.26 | -2.2 (-7.2, +2.2); 6/6 and 6/6 |

**Reading.** Every cost measure moves the right way and none is distinguishable from noise; the hook adds no turns (it pushes
nothing). Live `symbol` answers are rare, 9 per arm over 18 runs (top-1 on target 3 of 9 against 2 of 9), so even a perfect
ranking can touch few calls: agents make about one devkb navigation call per run. The per-cell swings (#118: 25.0 against 17.3
turns) are larger than 9 queries can explain and are run-to-run noise. This batch's `rmain` (20.6 turns) is also well above
the earlier waves' (17.8), so the comparison holds only within the batch.

**What it supports.** The ranking is correct on the recorded queries and costs nothing at run time, so it is safe to ship. It
does not by itself change what agents do; the bound is how seldom they ask.

---

# Update 2 (2026-11-21): the guardrail fixes, replayed offline

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
