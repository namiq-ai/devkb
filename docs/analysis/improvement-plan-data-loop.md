# Improvement plan: the external evaluation checked against the data, and a do / benchmark / evaluate / decide loop

Inputs: the external "Evaluation & Gap Analysis" of the improvement log, the benchmark record in
`docs/analysis/workflow-router-benchmark.md`, and the replays run since (`bench/policy/replay_queries.py`,
`hook_replay.py`, `stale_replay.py`, `inline_replay.py`). Everything quoted is from runs on disk; "estimate" marks my judgement.

## 1. The evaluation, item by item

Verdict: **confirmed** (matches the data), **corrected** (right direction, wrong number or cause), **overstated**, **unsupported**
(no data either way).

### 1.1 Findings

| claim | verdict | evidence and correction |
|---|---|---|
| hook fires, `DEVKB_ROUTER=0` falls back | confirmed | headless run: router on answered, off said NO CONTEXT. The router is `devkb/router.py`; `hook.py:73` is `pre_edit`, a different hook |
| false `located`/ticket-key bypasses fixed; 27 usage-limit runs archived; self-inflicted flags isolated | confirmed | commits `3e37948`, `5932278`; `runs-archive/` |
| refetch 39-40% | **corrected** | the first metric counted generic words and the by-design outline-then-read. Corrected (`storybench.refetch`): 14 of 76 queries (18%; an independent recount gives 73); `router` 33%, `rmain` 25%, `ctx` 7%; plus 19 outline-then-read, counted apart |
| `ctx` "significantly improved" symbol top-1, 51% -> 81% | **withdrawn (errata 2)** | one query counted 11 times; at function level 1 of 8 before and after; the live `ctx` arm never ran the ranking, so its -2.8 turns (within-ticket interval -4.9 to -0.8; unpaired -6.6 to +1.0) is an A/A noise floor, not an effect |
| 90 valid runs in a "30-row" snapshot | **corrected** | the table has 32 rows, 96 runs (6 tickets x 2 forms x up to 4 arms, 3 reps), none invalid |
| turns/cost: none 18.6, rmain 17.8, router 20.3 | **corrected (errata 3)** | the 17.8 mixed in a wave that was later discarded. On the runs on disk, 24 per arm: none 18.6 turns / $0.41, rmain 19.5 / $0.40, router 20.3 / $0.45; the router is +0.8 turns and +13% cost against rmain, in a different wave from it; SD within a cell is 3.8 (4.6 in the later batch) |
| ~1.1-1.5 devkb calls vs 6-7.5 greps | confirmed | rmain 1.5, router 1.1; grep 6.0-6.8 |
| 47% of greps answerable, 51% not | **corrected: 29% distinctive symbols** (`nav_habits.py`) | 394 greps: 47% name a graph symbol (23% `def X`, 24% identifier), 51% a field, keyword, common word or text |
| 256 decisions: 24 answered, 101 not-complete, 46 stale, 56 duplicate | confirmed | but the replay on base trees answered 54 of 381 (14%) |
| "29 of the 101 had a complete name; 20 of the 46 stale had all names complete" as recoverable | **corrected** | replayed: partial answers add 21 answers that sit *beside* grep (replace nothing); a name-scoped staleness rule frees 15 of 394 searches |
| outline -> ranged Read -> grep "adds overhead", refetch "due to uninformative outline" | **corrected** | 17 of 18 Reads after an outline were ranged: the outline did its job. Devkb arms pulled fewer characters of locating output per run: -15% (-9.0k) for rmain against none, -7% to -26% on every ticket (first figure -18%, from the discarded wave) |
| 70% of steps are reading, editing, tests | confirmed (about 78% of calls) | edit/write/test 13-17 of 27-32 calls per run |
| #205 withheld pass 3/3 (none) vs 5/9 devkb arms | confirmed, unexplained | devkb calls on #205 are 0.0-0.3 per run, so devkb navigation does not explain it; n = 3 |

### 1.2 Gap matrix

| area | evaluation's rating | rating from the data | why |
|---|---|---|---|
| 1 token budget | minor | **outline: moderate**; router: closed | router cap 3000 chars is inside 800 tokens; outline median 3.0-3.4k chars (~850 tokens), 5.9k (~1.5k tokens) on large files |
| 2 staleness | major | **minor by measured effect** | 70% of searches precede the first edit; recovering the rest is 15 of 394 (4%); a full rebuild is 12-13 s against the hook's 20 s |
| 3 gating | closed | confirmed closed | |
| 4 issue triage | major | **not supported by QB2** | the schema already has `ErrorSignature` (84 nodes), `SIMILAR_TO`, `DUPLICATE_OF`; the GitHub layer does not fill the last two. Text retrieval alone reaches 0.78 recall@5 on the hardest slice and the graph arm is worse (`qb2-baseline.md`) |
| 5 epic -> features | major | **closed by QB4** | the baseline already reaches 0.95 recall@20 on this repository; the graph arm is not better (`qb4-baseline.md`) |
| 6 issue -> PR | moderate: "lacks fuzzy matching" | **corrected** | `symbol` has prefix, word and edit-similarity tiers; the failures were generic words that exist as unrelated symbols (`merge`, `overload`) and ambiguity, now ranked by the task |
| 7 CR -> PR | moderate: "no blast radius" | **overstated** | `pack change`/`refactor` return callers at any depth and the tests; the real gap is that `tests_for` under-lists |
| 8 PR -> release | major | **not supported by QB3** | no breaking change exists in 16 releases; the cheap `ast` surface diff separates the additive ones, and the heuristics' problem is false alarms (`qb3-baseline.md`) |
| 9 delivery | major: "must inject inline" | **overstated** | `pre_edit` already pushes the pack of a file about to be edited. Inline delivery for Read, replayed: fails its gate (section 3) |

## 2. The measurement problem comes first

Within one ticket the standard deviation is 3.8 turns in the first four-ticket waves and **4.6 in the latest 36-run batch** (mean
19.1 turns; $0.065 on a $0.36 mean). Runs needed per arm at alpha 0.05, power 0.8, from the latest batch (corrected 2026-11-21;
the first version used 3.8 and 0.06):

| effect to detect | turns | cost |
|---|---|---|
| 15% | 41 | 23 |
| 10% | 91 | 52 |
| 5% | 365 | 206 |
| 2% | 2283 | 1288 |

Three arms at 91 runs and $0.40 each is about $110 for one 10% question; two arms about $73. The levers on the table are each worth 1-5%, so a live
batch cannot decide them. **Offline replays decide; live batches confirm only a claim of 10% or more.**

## 3. Estimated improvement per item (my judgement, with the data behind it)

Headroom: about 14 of 27 calls per run are navigation (grep, read, sed, devkb). About 29% of greps (3.0 patterns per run; distinctive symbols only) ask what the
graph holds; devkb replaced about 1.1 net.

| item | expected effect on turns | on tokens | basis | status |
|---|---|---|---|---|
| ship the ranking (`ctx`) | not shown | none | replay: 8 distinct queries, function level 1 of 8 before and after; held-out unchanged; the live `ctx` arm never ran it (errata 2) | **unproven; not installed by default** |
| silent context hook as the `init` default, router off | 0 | -2.5k first call if the router text is dropped | the router showed +0.8 turns and +13% cost against rmain (n.s., different waves); the context hook pushes nothing and its ranking is unproven | **superseded: no prompt hook is installed by default** |
| partial-answer guardrail | 0 | +20 tokens per run | replayed: +14 answers (14.0% to 18.6%), beside grep, none replaces a call | **killed** |
| refresh a stale graph | 0 | 0 | 12-13 s per rebuild; name-scoped rule frees under 4% | **killed** |
| inline pack on Read/Edit | at most 1.5% | **+2.4k tokens per run**, re-read each later turn (~4% of context) | `inline_replay.py`: 1.2 of 7.6 navigation calls per run are covered by an opened file's pack (39 reads of a file the pack merely names, which the agent still reads, and 44 greps). A pack is about 3.8k characters | **killed at the gate** |
| ambiguous `symbol --source`: do not print the body of a wrong first match | under 1% | -1 to -2k tokens on ambiguous names only | replay: `symbol resolve --source` printed `project_context.resolve` | **dropped** (5 of 8 distinct ambiguous queries would save a body, 3 would cost a call) |
| one call for outline plus the range | 1-2% | -0.5k | 0.25 outline-then-ranged-Read pairs per run | low value, skip unless a gate shows more |
| tests-to-run recall / quality | unknown | unknown | no ground truth yet: the fixes add tests, they do not change existing ones | needs a benchmark |
| triage, epic and release graph | not measurable on these tickets | | the tickets are fixes and features | needs its own benchmarks (4) |

**The honest total:** the navigation items together are worth 3-5% of turns and 5-10% of context at best, below what any live
batch here can detect. The reference architecture's value is where grep cannot reach: triage, epic and release questions. That
is a quality claim, and no benchmark here measures it yet.

## 4. The loop

Each backlog item runs the same loop. A step that fails its gate ends the loop for that item.

1. **Hypothesis.** One sentence, the metric it moves, the expected size (table above).
2. **Offline gate (free).** A replay on recorded runs or a ground-truth set. Pass if the metric moves by the stated amount and
   nothing else regresses. This is where most items are decided.
3. **Do.** Implement behind a flag; tests; one commit.
4. **Pilot.** Same-batch paired arms, at least 5 reps per cell, on tickets that name code or an error but no file, plus held-out
   tickets the change was never tuned on. All arms in one shuffled batch on one devkb commit (the harness skips a run whose
   directory exists: archive or fix before a batch, and check the log for `skip`).
5. **Evaluate.** Report every arm, run and failure. Quality first (pass rate and the hidden check), then calls, then tokens and
   cost with intervals. No claim from a cell of three.
6. **Decide.** Ship if the gate passed and the pilot shows no quality loss; iterate if the sign is right but unproven; kill if the
   gate failed. A claim of 10% or more earns a powered batch (section 2).

## 5. Backlog, in order

*The plan as first written, before the audits. Its status is the table at the end of this document ("Status after the audit and the fixes"): rows 1 and 3 were superseded (no prompt hook by default; the ranking is judged by replay), 2 was dropped, 4 to 7 were built as QB1 to QB4, and 8 was filed as #399 and #400.*

| # | item | gate (offline) | owner action | result so far |
|---|---|---|---|---|
| 0 | hygiene: full suite green (**1231 passed, 2 skipped on 2026-11-21**; first written as "1216"); the `.mcp.json` test checks what git tracks; refuse or archive on a run-name collision; `policybench.py score` per ticket | suite passes | done: 1216 tests, `.mcp.json` test fixed | `score` and the collision check open |
| 1 | `init` installs the silent context hook by default; the router becomes `--router` | `test_devkb_init`; the hook pushes nothing | do | pending |
| 2 | ambiguous `symbol`: no wrong body | replay `symbol --source` on 118: no wrong body printed, the right file listed | do | pending |
| 3 | held-out replay set: run `none` and `rmain` on 10 new navigation tickets, keep their queries | at least 100 `symbol`/`uses` queries from tickets the ranking never saw | do, then re-run `replay_queries.py` | **this is what tests the 51% -> 81% claim** |
| 4 | quality benchmark for `tests_for` and blast radius: take past fixes, revert the source change, ask whether `pack` names a test that then fails | recall of the failing tests; today unmeasured | design first | open |
| 5 | triage benchmark: closed duplicate issues of this repository as ground truth | precision and recall of a duplicate lookup, with and without the graph | design first | open |
| 6 | release benchmark: past tags with known breaking changes in `CHANGELOG` | does the audit flag them, and name nothing that did not break | design first | open |
| 7 | epic benchmark: past epics and the files their features changed | overlap of the predicted impact set with the real one | design first | open |
| 8 | graph defects: `pack error` lists raisers whose files lack the message and prints no Coverage warning; `tests_for` under-lists and says "no test calls it" for functions reached through their callers | reproduce each on a fixture | **drafts need your approval before posting to GitHub** | open |

Items 4-7 are the reference architecture's case. Their gate is a ground-truth set, so they can be decided offline, and they can
show a quality gain that turn counts cannot.

## 6. Killed or parked, with the data

- Prompt-time router push: no effect on cost, turns or quality in 72 runs (keep off).
- Partial-answer guardrail: `hook_replay.py`, +14 answers beside grep, 0 replaced.
- Fast refresh on stale graph: 12-13 s per build; `stale_replay.py` 6 of 690.
- Inline pack on Read: `inline_replay.py`, +2.4k tokens per run for at most 0.5 greps saved.

---

# Status after the audit and the fixes (2026-11-21)

Three independent audits (live batch, replay tools, quality benchmarks) found no wrong headline in the live table but several
overstated or irreproducible figures; all are corrected in `workflow-router-benchmark.md` (errata and errata 2). What the loop decided:

| item | result | status |
|---|---|---|
| ranking by the task's words | replay: one distinct query flips at file level, none at function level, held-out unchanged; the live `ctx` arm never ran it (an A/A: -2.8 turns between identical treatments is the design's noise floor) | **unproven; no prompt hook is installed by default** (`--prompt-hook context` is opt-in) |
| prompt-time router | no effect on cost, turns or quality in 72 runs | off by default (opt-in `--prompt-hook router`) |
| guardrail partial answers, refresh on stale graph, inline pack on Read | +14 hints beside grep; 6 of 690 searches; 1.2 covered calls per run against 2.3k tokens | killed at the offline gates |
| QB1 tests to run | **`pack` changes: 0.83 recall pooled over 23 items (10 held-out), import 0.64, grep 0.69, at precision 0.63** | **shipped on the branch**: `pack refactor` names tests that mention the function with no resolved call and says Incomplete; `pack file` marks direct tests |
| QB2 related issues | hybrid - text = +0.00; text 0.78 on first-time parents, structural 0.59 | issue-graph schema parked |
| QB3 release audit | 0 breaking changes in 16 releases; the heuristics produce false alarms (6 and 10 of 16) | no PublicAPI/DBSchema schema; a mechanical surface diff is the tool if one is wanted |
| QB4 epic impact | baseline 0.95 recall@20 (saturated), graph 0.84 | closed; no GOVERNS work |
| graph-defect tickets | reproduced and **filed as #399 and #400** (`ticket-drafts-graph-defects.md`) | open |
| harness | refuse-not-skip on collisions, `POLICY_BASES` for interleaved batches, archive is not contamination, refetch metric fixed, `--compare` with within-ticket intervals | done |

Dropped, with the reason: the ambiguous `symbol --source` change (5 of 8 distinct ambiguous queries would save a wrong body and 3 of 8
would cost a call; no net evidence); the Python tuple-unpack attribution (about 8 distinct pairs, about 2 points of recall; the mention
section covers it at the pack level); the interleaved 90-run live batch (nothing in the live data needs it, and the ranking it would test
is not what the agent runs).

Still open, in order of value:
1. **A live benchmark whose agent runs the arm's devkb.** In the current harness the agent's `devkb` is the checkout's own, which on these
   tickets is the code under edit, so no devkb change can be tested live. Tickets in another repository (the C/C++ corpora, whose bug
   fixes can be built from their own history) would separate the two.
2. Fix the two graph defects filed as #399 and #400.
3. Re-run QB1 when new snapshots accumulate: 23 items from 6 snapshots; some items share changed functions.

## Reconciliation of figures quoted in more than one place (2026-11-21, after the specification owner's review)
- **QB1 baselines.** Import 0.64 / grep 0.69 are the *23-item* pool (13 tuning + 10 held-out); import 0.65 / grep 0.72 are the *27-item* comparison (13 tuning + 14 held-out, `qb1_compare.py`). Both are right for their set. The shipped-over-original gain is +0.07 on all 27 and +0.04 on the 14 held-out (interval touches zero); the "+0.05" on 10 held-out items belongs to the earlier set.
- **Searches the graph could answer after a refresh: 6 of 690** (`stale_replay.py`, re-run today). Any "689" is the older count.
- **Inline pack on Read: +2.4k tokens** for 1.2 covered calls of 7.6 navigation calls per run (about 16%); "2.3k" was a rounding of the earlier 2.35k.
- **"72 runs" for the router** are the 24 runs of each of three arms (`none`, `rmain`, `router`) on four tickets; the snapshot holds 96 runs, because the ranking arm `ctx` (12 runs) and the other tickets are not in that comparison.
- **Staleness.** A full `devkb build` (12-13 s) was tested and killed. A single-file incremental refresh was not built: even at zero cost it can free at most the 6 of 690 searches, under 1% of calls.
- **QB2 and QB3 scope.** QB2 tested related-issue retrieval only (so parking `SIMILAR_TO`/`DUPLICATE_OF` is supported); it did not test error-to-raiser triage, which is `pack error`, measured by QB5 (`bench/quality/qb5_error.py`, #399). QB3 shows the existing release heuristics raise false breaking alarms (6 and 10 of 16); that argues for a plain AST public-surface diff, not for new graph schema.
