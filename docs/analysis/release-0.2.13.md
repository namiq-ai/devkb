# Release 0.2.13: search intent, the hook that teaches, and a benchmark that can be trusted (2026-11-19)

Questions: how is devkb wired into an agent's development work, and what did each part do to cost and quality? Did
the 0.2.13 stories (SPEC-DKB-007, S1–S5) make the hook's answers right and small? Can the benchmark's numbers be
trusted? And what should come next?

The milestone's goal, set by the owner: devkb's efficiency on saving and quality, and a benchmark framework whose logic
is reliable. 54 tickets are closed. Raw data and scripts: `bench/results/2026-11-19-release-0.2.13/`.

## Summary

- **The hook now answers the question the search asks.** On 973 recorded searches, the 0.2.12 hook answered 120, and
  52 of those answered a different question. After S3 and S4, none of 43 judged answers does (one judge artefact),
  under the spec's 5% floor. Answer text fell from 150k to 41k characters. The cut comes from no longer adding answers
  that only repeat grep's lines: 70 of those are dropped now.
- **Quality, not cost, on the release's own tickets.** Over 24 benchmarked tickets (72 runs per arm, Sonnet), the hook
  as of each batch passed 57 of 72 runs against 51 without devkb. v0.2.12's hook passed 58. Cost was flat: −0.6%
  against no devkb, with −3.8% context and −4.7% turns.
- **Agents do not use devkb unless an answer shows them how.** With the hook alone, agents made 0.17 direct devkb
  navigation queries a run. When each answer ends with the command that gives it (D1), agents made 1.50, in 9 of 18
  runs, and cost fell 11%, context 15% and turns 10%. D1 is now on by default (#267). D2, an outline on first open,
  changed nothing useful and was dropped.
- **Turns drive cost, and most of a turn is fixed load.** Cost follows turns (r = 0.92). A model call costs about
  $0.017 and re-reads about 41k tokens. 26.7k of those are present from the first call (system prompt, tools,
  instructions, ticket), and that fixed load makes up about two-thirds of everything a run reads. devkb adds none of it.
  A hook answer is about 1% of one turn's context: an answer that saves a turn is worth far more than a smaller answer.
- **The benchmark had to be fixed while it measured.**
  - Six hidden checks asked for more than their tickets did.
  - Three counts were wrong: turns, output tokens, and devkb navigation.
  - Three races lost or broke runs.
  - Load made suites fail that pass alone.

  Each one is fixed, and every figure in this report comes from the corrected data (§5).

## 1. How devkb is wired into an agent's work

devkb reaches an agent through five mechanisms. Only the first two are visible in the agent's own context before it
acts.

| Mechanism | When it acts | What the agent gets | State after 0.2.13 |
|---|---|---|---|
| **Instructions** (`AGENTS.md`, the devkb block `devkb init` writes) | at session start, in the fixed load | the table "you are about to… use…" | unchanged; part of the 26.7k fixed tokens |
| **Search guardrail** (`scripts/devkb_guardrail.py`, PreToolUse on Grep, grep/rg/git grep, Read) | before each code search | the graph's answer to the search's intent, alongside grep's output or, when complete, instead of it | answers by intent (S3), compact (S4), never on a stale graph (#182) |
| **Teach line, D1** (part of the guardrail) | at the end of each answer | `Next time ask devkb directly: devkb symbol X --source --project .` | **on by default** (#267); `DEVKB_GUARDRAIL_TEACH=0` turns it off |
| **Outline on first open, D2** | the first whole-file Read of a long code file | the file's outline | measured and dropped (#218); off |
| **Miss log** (PostToolUse) | after a search devkb could not answer and grep found code | nothing; a line in `.devkb/graph-misses.jsonl` | logs the real reason and the enclosing function (#187, #137, #138) |

The guardrail's path, since S1–S4:

1. **Classify the search's intent** (`classify()`), one of 13 classes from the search's own command part: read a body,
   locate a definition, list a file's symbols, call sites (plain, filtered, in one file), count, list files, invert,
   literal text, non-code, unknown, not a search (S1, S2, S3).
2. **Ask the graph question for that intent:**
   - `symbol --source` for a body or a definition;
   - `outline` for a file's symbols;
   - `uses` for call sites, with the pipe's filter applied to paths;
   - nothing for counts, file lists, inverted searches and literal text.

   Before S3, every name got `pack refactor`, which is repository-wide callers.
3. **Shape the answer like grep's** (S4): `file:line: text` lines, one wrapper line, at most 1,500 characters. Nothing
   is added when the lines would only repeat grep's output.
4. **Decide the action:**
   - replace when the answer is complete and the graph is current;
   - otherwise add it beside grep's output;
   - otherwise pass through, and the miss log records it.
5. **Teach (D1):** append the one devkb command that gives this answer.

## 2. What the stories changed in the answers

The same 973 searches (recorded in the 0.2.12 benchmark sessions) replayed through the hook of each version. This is
deterministic: no agent is involved.

| Hook | Searches answered | Answers to the search's question | Answer text |
|---|---|---|---|
| v0.2.12 | 120 | 34 same, 34 partly, 52 different | 150k chars |
| S3 (#216): a graph question per intent | 110 | 100 of 101 judged | 92k |
| S4 (#217) and S5: grep-shaped, no duplicates | 52 answered, 70 dropped as repeats | 42 of 43 judged (1 artefact) | 41k |
| + #175: string keys | 15 more key searches answered alongside, pass-throughs 357 → 341 | | |

S1 (#214) only adds `intent` and `question` to each decision line. S2 (#215) stops keywords, other-case words and
option values from being read as names. Both are in the S3 row.

## 3. What agents did: the tri-mode benchmark

### Method

- **Three arms per ticket,** each on the same main commit and in the same batch:
  - no devkb (`nonekeep`);
  - the v0.2.12 release's devkb and hook (`release`);
  - the hook as it stood on main in that batch (`main`).
- **Runs:** 3 per arm, Sonnet. The agent implements the ticket as filed, in a fresh checkout.
- **Scoring:**
  - a hidden check per ticket, removed from the agent's checkout, run on the finished checkout;
  - the full suite, with failed tests re-run once (#260);
  - the transcript, recounted with the corrected rules (#258).
- **The devkb under test:** each devkb arm takes its devkb from a tool environment built at an exact commit, never
  from the checkout the agent edits.
- **The last batch** (6 tickets) added the D1 (`teach`) and D2 (`outline`) arms.

### Per ticket

| Ticket | Hidden check: none / v0.2.12 / main | Cost per run: none / v0.2.12 / main | main against none: cost, context, turns |
|---|---|---|---|
| #194 | 3/3 / 3/3 / 3/3 | $0.23 / $0.16 / $0.19 | −17%, −16%, −13% |
| #195 | 3/3 / 3/3 / 3/3 | $0.17 / $0.15 / $0.15 | −11%, −17%, −15% |
| #214 | 2/3 / 3/3 / 2/3 | $0.73 / $0.66 / $0.67 | −7%, −14%, −12% |
| #215 | 3/3 / 3/3 / 3/3 | $0.35 / $0.38 / $0.33 | −8%, −7%, −2% |
| #193 | 2/3 / 3/3 / 2/3 | $0.23 / $0.25 / $0.27 | +17%, +30%, +20% |
| #216 | 0/3 / 0/3 / 1/3 | $1.51 / $1.67 / $1.86 | +23%, +29%, +12% |
| #128 | 3/3 / 3/3 / 3/3 | $0.17 / $0.21 / $0.19 | +7%, +8%, +2% |
| #189 | 1/3 / 3/3 / 3/3 | $0.21 / $0.20 / $0.20 | −2%, −21%, −20% |
| #192 | 1/3 / 3/3 / 2/3 | $0.24 / $0.41 / $0.23 | −3%, +0%, +2% |
| #196 | 2/3 / 3/3 / 2/3 | $0.36 / $0.29 / $0.34 | −5%, −16%, −15% |
| #198 | 1/3 / 1/3 / 2/3 | $0.33 / $0.27 / $0.28 | −14%, −27%, −27% |
| #201 | 3/3 / 3/3 / 3/3 | $0.28 / $0.29 / $0.28 | +3%, −5%, −4% |
| #204 | 3/3 / 3/3 / 3/3 | $0.14 / $0.20 / $0.17 | +23%, +45%, +37% |
| #212 | 3/3 / 3/3 / 3/3 | $0.16 / $0.17 / $0.15 | −4%, −1%, −3% |
| #217 | 0/3 / 0/3 / 0/3 | $0.36 / $0.29 / $0.26 | −27%, −41%, −23% |
| #228 | 3/3 / 3/3 / 3/3 | $0.21 / $0.22 / $0.22 | +6%, +4%, +4% |
| #182 | 3/3 / 3/3 / 3/3 | $0.28 / $0.29 / $0.26 | −9%, −28%, −27% |
| #187 | 2/3 / 1/3 / 2/3 | $0.28 / $0.30 / $0.29 | +1%, −3%, −4% |
| #203 | 3/3 / 3/3 / 3/3 | $0.30 / $0.27 / $0.34 | +14%, +19%, +13% |
| #118 | 3/3 / 3/3 / 3/3 | $0.49 / $0.43 / $0.59 | +22%, +18%, +6% |
| #120 | 2/3 / 3/3 / 2/3 | $0.69 / $0.85 / $0.81 | +18%, +53%, +26% |
| #205 | 3/3 / 2/3 / 3/3 | $0.52 / $0.52 / $0.44 | −14%, −19%, −16% |
| #137 | 0/3 / 0/3 / 0/3 | $0.37 / $0.40 / $0.40 | +6%, +5%, +0% |
| #175 | 2/3 / 3/3 / 3/3 | $0.28 / $0.29 / $0.25 | −12%, −25%, −22% |
| **24 tickets** | **51/72 / 58/72 / 57/72** | | **−0.6%, −3.8%, −4.7%** (geometric mean) |

A pass needs both the hidden check and a green suite. With 3 runs per arm, almost every single-ticket cost difference
is within noise. The release-wide line is the one to read.

- **Quality improves; cost does not move.** Both devkb arms pass 6–7 more runs than no devkb. Main is cheaper on 13 of
  24 tickets, v0.2.12 on 9.
- **#216, #217 and #137 fail on every arm.** These are agent gaps, not hook effects:
  - #216 is the largest story;
  - #217's runs miss a rule the ticket did not state (it is in the ticket now);
  - #137's runs miss a one-file grep with options.

### Through the stories: main against v0.2.12 in the same batch

| Main's devkb at | Tickets | Cost | Context | Turns | Hook text a run |
|---|---|---|---|---|---|
| before S1 | 3 | +7% | +15% | +13% | 1,136 against 2,122 chars |
| S1 | 1 | −14% | −11% | 0% | 4,348 against 3,679 |
| S2 | 2 | +8% | +21% | +17% | 1,578 against 2,388 |
| **S3** | **10** | **−8%** | **−8%** | **−6%** | **394 against 1,155** |
| S5 | 2 | −7% | −15% | −10% | 205 against 2,683 |

Only S3 has enough tickets to read on its own.

### D1 and D2 (#218): the last batch, 6 tickets, 18 runs per arm

| Arm | devkb navigation queries a run | Runs with any | Cost against hook only | Context | Turns | grep calls | Hidden check | Suite |
|---|---|---|---|---|---|---|---|---|
| hook only | 0.17 | 3 of 18 | — | — | — | — | 14/18 | 18/18 |
| **hook + D1** | **1.50** | **9 of 18** | **−11%** | **−15%** | **−10%** | +1% | 15/18 | 18/18 |
| hook + D2 | 0.47 | 4 of 17 | +1% | +3% | +1% | +18% | 14/18 | 16/18 |

A hand-check of 20 saved answers: 20 answer the question the search's intent names, and 1 may be partial.

## 4. Insights

**Turns are the cost.**
- Over 252 runs, cost correlates with turns (r = 0.92), context (0.98) and output tokens (0.99). Context is 98.9% of
  all tokens.
- A model call costs a median $0.017 and re-reads 41k tokens.
- So the useful question about any hook answer is whether it saves a turn, by replacing a search or making the next
  one unnecessary. Its size matters much less.

**The fixed load is two-thirds of every run.**
- The first model call already carries 26.7k tokens: system prompt, tool definitions, instructions, ticket. It is the
  same on every arm, so devkb adds nothing to it.
- Re-read on every turn, that load is 55–68% of a run's context.
- Every 1k tokens cut from it saves about 2.5% of each turn's context. That is more than the whole S4 cut of answer
  text saves in a typical run.

**Answer quality matters more than answer size.**
- A 1,500-character answer (about 400 tokens) is about 1% of one turn's context.
- The S3 batches' −8% is likely more than smaller text, which by itself saves under 1%. Our reading, not measured
  directly: agents stopped following answers to the wrong question. Before S3, a body read got repository-wide callers,
  and the agent read on to find the body anyway.

**Teaching beats answering.**
- With the hook alone, grep calls stay at 4–8 a run on every arm: agents keep searching however good the answer.
- One line naming the devkb command made half the runs use devkb directly, with fewer turns.
- That line sits where the agent is looking at the moment of need. The instructions at session start do not.

**The hook's own time does not matter.**
- Measured on 150 recorded searches: 105 ms median for a search it passes through, 0.8 s for one it answers, 0.85–1.2 s
  at the 90th percentile.
- A model call in these runs takes about 17 s.

**Load changes results.**
- Running two batches at once doubled suite times, from 2.5 to 4 minutes, and made suites fail that pass alone: 4 of 9
  in the #187 batch.
- It also inflates wall time evenly across arms. Compare arms within one batch, never across batches.

**Self-hosting confounds the counts.**
- The repository the agents edit is devkb itself, so agents run devkb to test their change.
- A devkb command is navigation only before the run's first edit of devkb's code (#258). Without that rule, the
  no-devkb arm seemed to "use devkb" 3.7 times a run.

## 5. How reliable the benchmark is now

What went wrong during 0.2.13, and what fixed it:

| Problem | Effect | Fix |
|---|---|---|
| Hidden checks asking more than the ticket (#193, #196, #216, #217, #205, #137) | tickets scored 0/9 that agents had solved | each check re-read against its ticket's "Expected"; corrected checks fail on main and pass on the fix; every run re-judged |
| `turns` and `out_tokens` from the session's last message | turns read 1, output 59 tokens instead of 4,849 | session totals from `modelUsage`, turns = model calls (#258) |
| devkb self-tests counted as navigation, then navigation counted as self-tests | "devkb use" wrong in both directions | before the first edit of devkb's code it is navigation; after it, a self-test (#258, #263) |
| Two processes building the same template | 12 runs refused, one checkout cut in half | templates and tool environments locked across processes (#243) |
| An uncaught error in one run's thread | the batch log stopped; one run never started | every run error recorded as that run's end (#245) |
| Suites that fail only under load | runs scored red for correct changes | failed tests re-run once; flaky runs shown apart (#260) |
| Setup repeated for every run | 4–5 minutes of setup a run | one prepared checkout per arm and commit, copied in 0.9 s; scoring as runs end; 8 runs at a time (#239) |

A tri-mode batch of two tickets took 1–2.5 hours before. The last batch, 90 runs over 6 tickets and 5 arms, took
about 1.5 hours while sharing the machine with another batch. Before each batch, every hidden check was run on that
batch's main commit to show it fails there. This is a manual step today; action 5 below makes it a routine.

**Corrections to figures given during the work.** Output tokens were first reported as 0.8–1.2k a run, from per-message
usage, which is partial. The session totals give 6–34k. Direct devkb use was first reported as 0.00 on every arm, under
#261's rule, which #263 corrected.

## 6. Where devkb stands, what is next, and actions

**Now.**
- The hook answers the right question in a grep-like shape, never on a stale graph, and teaches its command.
- It buys quality (+6 passed runs of 72 against no devkb) at equal cost on small tickets, and −11% cost once it
  teaches.
- The benchmark measures that with every known counting error fixed. With 3 runs per arm, a single-ticket difference
  of up to about 20% is within noise; release-wide means over 24 tickets are the reliable figures.

**Next, by expected effect:**

1. **Measure D1 as shipped, on larger tickets.** The D1 result rests on 6 tickets of $0.25–0.85. Rerun hook with D1
   against `noteach` on the next release's tickets, and add tickets with more navigation (#216-sized), where the
   benchmark has the most to measure.
2. **Cut the fixed load.** It is two-thirds of every run. Measure what the instructions and tool definitions cost per
   turn, and test a shorter devkb block and a smaller tool list as arms. A 2–3k token cut would save more than any
   answer change so far.
3. **Make answers save turns:**
   - replace more often where the answer is complete: today 18 of 52 answers replace;
   - lower pass-throughs (1.4–1.7 a run, mostly `not-complete`) by closing graph gaps: #244 for C++, and the reasons
     the miss log records.
4. **Teach beyond the hook.** D1 works because it acts at the moment of need. The same line could go into the
   pre-edit pack and into a "no graph answer" pass-through, as a measured candidate.
5. **Check the checks before a batch.** Six of the 0.2.13 checks asked more than their tickets. A review step that
   puts each check's cases next to the ticket's "Expected", before the batch, would have saved hours. Run it as part
   of the batch's "fails on main" proof.
6. **Benchmark beyond devkb's own repository.** Self-hosting confounds navigation counts. The registry's open-source
   repositories (`bench/repos.yaml`) have no such problem.

**Action items:**
- Refresh the user-level hook to 0.2.13. The local "substitution off" patch, kept until #180–#182, is no longer needed,
  and D1 is on with it.
- Decide the milestone of #244 (C++ implicit constructors, operators, indexed receivers and long chains).
- Add the `noteach` arm to the next release's batches.
- Track the fixed load (first-call tokens) in the release table.
