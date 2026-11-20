# Performance of the 0.2.14 benchmark: before and after the harness fixes, and the hand-off to 0.2.15 (2026-11-20)

This is the deliverable of 0.2.14's measurement stream: the same eight tickets (#301-#307, #331) measured twice. First on
the harness as it was (48 runs; every table and caveat in `benchmark-0.2.14-facts.md`), then on the final harness (16 runs,
one per arm and ticket, from each ticket's own base commit, the agents never seeing the fixes). It records what changed,
what did not, and what 0.2.15's efficiency work (epic #339) starts from. **Facts** come with their source; **inferences**
are marked. n is small everywhere: read the ranges, not only the means.

## 1. Summary

- **With the harness defects fixed, the extra cost of the devkb arm fell from +26% to -6% on average (+15% without one
  outlier).** Turns went from 16.5 to 9.1 per run and total context from 620k to 257k in the devkb arm; the no-devkb arm also
  fell (turns 11.2 to 9.0, context 363k to 276k, cost $0.190 to $0.149).
- **Most of the earlier "devkb costs more" was the benchmark, not devkb**: the arms ran different suites, the 120 s Bash timeout
  backgrounded the larger suite in every devkb run (24 of 24, none in the other arm), permission denials and missing
  reproduction data cost both arms retries, and agents could write into the harness repository. All of these are fixed and
  merged (section 3).
- **What did not change: devkb is still not used.** devkb nav is 0 in all 16 re-run runs (0 of 38 devkb-arm runs measured
  so far), the hook answered a search in 3 of 8 devkb runs, and the devkb setup still costs **+3.6k tokens (+20%) in the first
  call** (17.9k against 21.4k), carried in every later call.
- **The honest remaining gap is small and in devkb's disfavour**: without #331's no-devkb run (21 turns, $0.42, an outlier),
  the devkb arm is +21% turns, +38% context and +15% cost over the other seven tickets, and costlier on 6 of the 8 tickets.

## 2. The comparison

Means per run. "Before" is the 48-run baseline (3 runs per cell); "after" is the 16-run re-run (1 run per cell).

| Measure | none, before | none, after | change | devkb, before | devkb, after | change |
|---|---|---|---|---|---|---|
| Turns | 11.2 | 9.0 | -20% | 16.5 | 9.1 | -45% |
| Total context k | 363 | 276 | -24% | 620 | 257 | -59% |
| Cache-read k | 338 | 256 | -24% | 590 | 237 | -60% |
| Output k | 5.7 | 4.5 | -22% | 5.9 | 3.7 | -37% |
| Cost per run $ | 0.190 | 0.149 | -22% | 0.239 | 0.140 | -41% |
| Wall min | 2.7 | 3.0 | +11% | 5.7 | 2.8 | -51% |
| Permission denials | 3.7 | 1.5 | -60% | 3.1 | 1.6 | -47% |

| Measure (after) | none | devkb | difference |
|---|---|---|---|
| All 8 tickets: turns / context / cost | 9.0 / 276k / $0.149 | 9.1 / 257k / $0.140 | +1% / -7% / -6% |
| Without #331 (7 tickets): turns / context / cost | 7.3 / 172k / $0.110 | 8.9 / 238k / $0.128 | **+21% / +38% / +15%** |
| First-call context | 17.9k | 21.4k | **+3.6k (+20%)** |
| Hidden check | 7 of 8 | 8 of 8 | #305's none run failed the same assertion as in the baseline |
| Suite | 7 of 8 | 8 of 8 | #306's none run left a failing test it wrote itself |
| Commands backgrounded | 0 | 0 | before: 0 and 24 of 24 |
| Runs flagged as having changed the harness repository | 0 | 0 | before: 3 of 48 wrote into it |
| Calls aimed at the missing audit data, per run | 0.0 | 0.1 | before: 3.4 and 2.0 |

**Why the means in the first row must not be read alone** *(inferred, from the per-ticket rows below)*: the devkb arm is costlier on
#301, #302, #304, #305, #306 and #307, and cheaper on #303 and #331. #331's no-devkb run took 21 turns and 1002k context (the agent
changed five files); it alone lifts that arm's mean from $0.110 to $0.149. One run per cell cannot tell a ticket's difficulty
from an arm's effect.

## 3. What changed in the harness, and what each change did

| Change | PR | Measured effect |
|---|---|---|
| Both arms run the same suite (#331) | #333 | test counts equal per ticket in all 16 runs (674 to 698); before 675 against 986 |
| The Bash tool's timeout is 600 s in every arm (#334) | #341 | commands backgrounded: 24 of 24 devkb runs before, 0 of 16 after; waiting calls were 2.8 of the 3.5 extra tool calls per run |
| `.venv/bin/devkb` is allowed in the devkb arm, denied in none (#335) | #342 | no agent tried either form (0 devkb commands), so no change measured |
| A reproduction block whose data is missing becomes one line saying so (#336) | #343 | calls aimed at the missing data per run: 3.4 and 2.0 before, 0.0 and 0.1 after |
| Checkouts and templates live outside the repository; a change to it flags the run (#340) | #344 | 0 runs flagged, 0 writes into the harness repository (3 of 48 before) |
| Re-scoring one arm keeps the other arms' rows (#306); the template key includes the pre-registered hook (#307) | #345, #346 | correctness of the harness, no cost effect |
| The first reminder is not spent on a literal search (#329); the stream records what the hook said (#330) | #349, #350 | hook outputs recorded in 8 of 8 devkb runs (1 or 2 each), 0 in none; 7 of 21 earlier reminders had gone to literal searches |
| The none arm's own suite is green (#347) | #348 | no run refused as a red base after it |

Permission denials fell by about half in both arms but stayed at 1.5 per run: the checker still refuses compound commands, variables
and brace forms, and a `cd` into a subdirectory makes every allowed `.venv/bin/...` command unmatchable (seen once, #334's devkb run:
9 denials, 25 turns).

## 4. What the re-run says about devkb itself

1. **Use**: devkb was queried in 0 of 16 runs (0 of 38 devkb-arm runs so far, counting the earlier batches). The first tool call of the
   agents is a direct read of the file the ticket names; 32 of the 33 open tickets name one under "Where to start".
2. **The hook**: 8 devkb runs, 15 hook outputs recorded (reminders and answers), 3 answers beside grep.
   Both arms keep the policy's cost: the first call carries 3.6k tokens more (+20%).
3. **The setup is now the whole difference.** With equal suites, no timeout cliff and no wasted retries, the devkb arm pays for its
   policy text and reminders and, in these tickets, gets nothing back, because the work needs no navigation. This is the
   measurement 0.2.15's efficiency epic starts from.

## 5. Hand-off to 0.2.15 (epic #339)

| Item | Baseline from this report | Where |
|---|---|---|
| Overhead of offering devkb | first call +3.6k tokens (+20%); per run about +15% cost without the outlier | #339 |
| Make devkb useful where it matters | 0 queries in 38 devkb-arm runs; the earlier benchmark's chain questions saved 37% | #337 (revised) |
| The hook's answers | 3 of 8 runs had an answer; earlier 4 of 57 decisions; 20 `not-complete` pass-throughs | #339 |
| Permission denials | 1.5 per run; `cd` into a subdirectory defeats the allowlist | to file under #339 |
| A repetition rule | n=1 per cell here: the per-ticket sign flips (#331 -48% for devkb, #306 +30%) | #339 |
| A flaky timing test under load | `test_csharp_symbols.py::test_lambda_parameter_lookup_stays_linear_in_a_long_fluent_method` failed once in a loaded full suite and passed alone | to file |
| Build time stays linear (#289) | moved to 0.2.15 | #289 |

## 6. Per run (final harness; one run per arm)

| Ticket | Arm | Turns | Cache-read k | Output k | Total ctx k | Cost $ | Wall min | devkb nav | Remind / Pass / Answer | Hook outputs | Denials | Backgrounded | Tests | Hidden | Suite |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #301 | devkb | 8 | 183 | 2.9 | 198 | 0.110 | 2.4 | 0 | 0 / 0 / 0 | 1 | 2 | 0 | 674 | pass | pass |
| #301 | none | 6 | 117 | 2.7 | 130 | 0.089 | 2.5 | 0 | 0 / 0 / 0 | 0 | 0 | 0 | 674 | pass | pass |
| #302 | devkb | 13 | 335 | 5.5 | 355 | 0.166 | 0.7 | 0 | 1 / 0 / 0 | 1 | 6 | 0 | 685 | pass | pass |
| #302 | none | 8 | 178 | 3.5 | 196 | 0.123 | 2.4 | 0 | 0 / 0 / 0 | 0 | 1 | 0 | 685 | pass | pass |
| #303 | devkb | 6 | 140 | 2.3 | 157 | 0.107 | 2.3 | 0 | 1 / 1 / 1 | 2 | 0 | 0 | 689 | pass | pass |
| #303 | none | 7 | 153 | 3.8 | 170 | 0.119 | 2.3 | 0 | 0 / 0 / 0 | 0 | 1 | 0 | 689 | pass | pass |
| #304 | devkb | 6 | 133 | 1.4 | 148 | 0.086 | 2.5 | 0 | 1 / 1 / 1 | 2 | 0 | 0 | 692 | pass | pass |
| #304 | none | 5 | 95 | 2.3 | 107 | 0.081 | 2.1 | 0 | 0 / 0 / 0 | 0 | 1 | 0 | 692 | pass | pass |
| #305 | devkb | 10 | 270 | 5.0 | 292 | 0.168 | 3.4 | 0 | 1 / 0 / 0 | 1 | 2 | 0 | 694 | pass | pass |
| #305 | none | 7 | 160 | 4.0 | 181 | 0.136 | 3.0 | 0 | 0 / 0 / 0 | 0 | 1 | 0 | 694 | FAIL | pass |
| #306 | devkb | 10 | 242 | 3.2 | 259 | 0.126 | 3.9 | 0 | 1 / 1 / 0 | 1 | 0 | 0 | 698 | pass | pass |
| #306 | none | 8 | 158 | 2.9 | 171 | 0.098 | 3.6 | 0 | 0 / 0 / 0 | 0 | 1 | 0 | 698 | pass | FAIL |
| #307 | devkb | 9 | 238 | 3.0 | 259 | 0.138 | 3.5 | 0 | 1 / 4 / 0 | 1 | 1 | 0 | 698 | pass | pass |
| #307 | none | 10 | 235 | 3.4 | 252 | 0.126 | 3.5 | 0 | 0 / 0 / 0 | 0 | 2 | 0 | 698 | pass | pass |
| #331 | devkb | 11 | 359 | 6.8 | 389 | 0.224 | 3.8 | 0 | 1 / 4 / 1 | 2 | 2 | 0 | 698 | pass | pass |
| #331 | none | 21 | 954 | 13.5 | 1002 | 0.423 | 4.5 | 0 | 0 / 0 / 0 | 0 | 5 | 0 | 698 | pass | pass |

Means: none 9.0 turns, 276k, $0.149; devkb 9.1 turns, 257k, $0.140.

## 7. Data and how to reproduce

- Result rows: `bench/policy/rerun-0.2.14/results-*.jsonl` (the hook text in three rows had the checkout path replaced by `<checkout>`; #356 makes
  the harness do that itself). The 48-run baseline rows are `bench/policy/results-*.jsonl`.
- Tables: `python bench/policy/analysis_0214.py --results bench/policy/rerun-0.2.14 --runs <archive>/runs`; the token columns above come from the
  runs' `result` events (`modelUsage`).
- Archive of the 16 run streams: `devkb-benchmark-0.2.14-rerun-archive.tar.gz` next to the checkout (not committed: the streams hold local paths).
- Bases: #301 4155904, #302 7b4a75e, #303 4b656e1, #304 ed60bac, #305 ba63106, #306, #307, #331 2bb0c86. Harness: `main` at cb23644. Model: Sonnet 5.5.
