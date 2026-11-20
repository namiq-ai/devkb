# Why agents given devkb do not query it (#381, 2026-11-20)

**Question.** Agents that are given devkb (its policy in `AGENTS.md`, the guardrail hook, a built graph) almost never run a devkb query: 0 of 45 devkb-arm runs in 0.2.14, and 0 of 87 runs on the tickets worked since. Each lever tried so far was measured on its own and none moved it. This document puts the evidence together and ranks the causes. **Facts** have a source; *(inferred)* marks a reading.

**Data.**
- The 0.2.13 release batch: the transcripts of `main`, `teach` and `outline` runs on the six D1 tickets, still in `~/.claude/projects/*policy-work-p<ticket>-<arm>-r<n>/`, and the result rows in `bench/results/2026-11-19-release-0.2.13/results/`.
- The 0.2.14 baseline and re-run (`docs/analysis/performance-0.2.14.md`).
- The runs of #372, #371 and #375 and #375's 54-run keep-or-drop benchmark (the archive `devkb-benchmark-375-teach-archive.tar.gz`, next to the checkout).
- **81 interviews** (`bench/policy/interviews-381/answers.jsonl`). A devkb query is counted only when a command *runs* devkb (the first word of a shell segment), not when devkb appears as text inside an edit. The harness's own counter mixes the two (#309).

## 1. The answer, ranked

| # | Cause | Verdict | Evidence |
|---|---|---|---|
| 1 | **The ticket hands over the location, so a read is the shortest path** | **confirmed** (confounded; #337 separates it) | 0 of 87 runs tried devkb on tickets that give line numbers, against 19 of 54 on 0.2.13's tickets, which mostly do not (p ≈ 1e-9). 56 of 63 agents asked "why not" said the ticket named the file and lines. |
| 2 | **When agents did try, the harness refused the command** | **confirmed**, for 0.2.13 | In 0.2.13, 37 devkb attempts in 18 runs; **34 were refused** by the permission checker (mostly `cd … && devkb …`), and only 3 got an answer. Agents did retry (about 2 attempts a run), but in 15 of the 18 runs no attempt ever got an answer. 15 of the 18 interviewed agents said their command was refused. |
| 3 | **devkb's answer for the files these tickets change is incomplete** | **confirmed**, in one area that matters | `pack file` lists 0-1 tests for the bench files these tickets edit, against 2-11 test files that load them (#382). #302's agent failed a full run on a test devkb would not have named. |
| 4 | **Advice at the point of need is not followed** | **confirmed** | The teach line was seen 17 times in #375's `teachall` arm, with 0 queries. 15 of 63 agents said they saw the hook's devkb hint and did not act on it. |
| 5 | **The work is small and local, so the expected gain is small** | **reported**, consistent with the data | 32 of 63 said the fix was small or local. 40 judged devkb "would have helped a little", 17 "not at all", **0 "clearly"**. |
| 6 | Familiarity: grep and sed are free to recall, devkb is an unknown CLI | **open** | 7 of 63 said "habit" or "momentum". Not tested by an arm (SPEC-DKB-007 D3, intent-named native tools, was never built). |
| 7 | The model | **open** | Only Sonnet 5.5 has been measured. |

## 2. The 0.2.13 positive case was refused commands, not answers

0.2.13's D1 decision (#218) recorded 1.50 direct queries a run with the teach line against 0.17 without it, and turned the line on by default (#267). The transcripts show otherwise:

- **The prompt was byte-identical** across `main`, `teach` and `outline` for each ticket.
- **The first devkb call came at tool call 1 or 2** in every `teach` run that made one: `.venv/bin/devkb outline devkb/cpp_resolve.py`, `pack file …`, `uses _def_spans`. That is before any hook output could reach the agent, so at that moment the arms did not differ.

| Ticket | main: first devkb call at tool call | teach | outline |
|---|---|---|---|
| #118 | 7, none, none | 2, 1, none | none, 8, none |
| #120 | none, none, 3 | 1, 2, 2 | 1, 1, none |
| #137 | 13, none, none | none, none, 1 | none, none, 1 |
| #175 | none, none, none | none, none, 1 | none, none, none |
| #203 | 3, none, none | 1, 2, none | none, none, none |
| #205 | none, none, none | none, none, none | 1, none, none |

- **Runs that tried devkb:** main 4 of 18, teach 9 of 18, outline 6 of 18. Teach against main: two-sided Fisher exact **p = 0.16**.
- **Of the 37 attempts, 34 were refused** by the permission checker. Only 3 runs got an answer.
- **The 18 agents that tried, asked what made them reach for it:**
  - 11 said they reached for it because AGENTS.md says to ask the graph first.
  - 15 said the command was refused.
  - Of the other 3, 2 said the only devkb output they saw came from the hook, and 1 said it ran only devkb's build, not a query.

**Conclusion.** The policy text *did* bring agents to devkb at the start of a ticket that leaves a navigation step, and the benchmark refused them. The teach line had no part in that, and #375's direct test (17 lines seen against 7, 0 queries in both arms, +12.6% cost) agrees. D1 is still on by default for the answers the hook gives (#267). Whether to keep it is the owner's decision; this document records only that its measured basis does not hold.

## 3. The ticket's shape

| Set | Line numbers in "Where to start" | Named files | Runs that tried devkb |
|---|---|---|---|
| 0.2.13's six D1 tickets | 1 of 6 (#118, which spans three large C++ files) | `cpp_symbols.py` (1,299 lines), `devkb_guardrail.py` (1,573), `cpp_resolve.py` (521); classes and functions by name | **19 of 54** |
| 0.2.14's tickets, the re-run and the 11 tickets worked since | 11 of 11 (`L290-309`, `L131-136`, …) | bench files of 222-494 lines | **0 of 87** |

Fisher exact p ≈ 1e-9. **This is confounded:** different tickets, code areas (the C/C++ resolver against the bench harness), devkb versions, and the permission fixes of #334 and #335 between the two sets. *(inferred)*: with a line range the agent runs `sed -n A,Bp` straight away. A class or function name in a large file leaves a navigation step, and that is where the 0.2.13 agents ran `wc -l` and then `devkb outline`. #337's design (the same tickets with and without the location) is the test that separates the ticket's shape from the rest.

## 4. What agents say (81 interviews)

**Method.** Each finished session was resumed once (`claude -p --resume <session>`), in its own checkout, with no tools allowed and one turn, and asked one fixed question:
- **Runs that did not query devkb:** "You were working on this ticket in a repository that offered devkb (its AGENTS.md describes it; a hook may have shown a devkb command). You did not run devkb. In two or three sentences, why not? Name what you used instead and whether devkb would have helped. Answer in text only."
- **0.2.13's runs that did:** "You ran devkb during this ticket. In two or three sentences: what made you reach for it at that point, instead of grep or reading the file? Did its answer help, and would you use it again for this kind of task?"

Cost: $30.81 for 81 sessions (about $0.25 for a "why not" session, more for the larger 0.2.13 sessions).

**Limits.** The answers are reconstructed after the fact, and agents lean towards self-blame against AGENTS.md ("that was a lapse on my part"). So a claim here counts only when the run data agrees. Counts come from keyword rules checked against a sample of answers in each group; an answer can fall into several groups.

| "Why not" (63 answers) | Answers |
|---|---|
| The ticket named the file and lines | 56 |
| The fix was small or local | 32 |
| Saw the hook's devkb hint and did not act on it | 15 |
| Habit or momentum | 7 |
| A refused compound command pushed it to other tools | 7 |
| Named something concrete it missed | 8 |
| devkb "would have helped a little" / "would not have helped" / "would clearly have helped" | 40 / 17 / 0 |

**Checked against the data:**
- #302's agent said devkb would have shown `test_bench_run_measures_258.py` "before my first full run failed on it". The stream confirms the failure (`1 failed, 686 passed`, one extra fix-and-rerun cycle).
- But `devkb pack file bench/policy/storybench.py` at that base lists **0 tests**, so devkb would *not* have helped there (cause 3, #382). The agent's belief in devkb's value was more generous than devkb's answer.

## 5. What follows

- **#337, impact tickets without the location**, is the decisive experiment for cause 1. Run it before any further change to the policy text or the hook.
- **#382 (tests to run)** has to land before a benchmark can credit devkb with the "tests to run" value agents name most often.
- **#369 (permission denials)** and **#379 (the MCP config race)**: a refused or broken command is how 0.2.13's real attempts ended.
- **D3 (intent-named native tools)** is the untested candidate for cause 6.
- **One model only** (cause 7): a second model on the same nine tickets would show whether these findings hold beyond Sonnet.
- **D1's default (#267)** rests on the 0.2.13 numbers in section 2. Keeping it is the owner's call, with that basis gone.

## 6. Data

- **Interviews:** `bench/policy/interviews-381/answers.jsonl` (run, question, answer and cost; paths redacted, no session ids).
- **0.2.13 transcripts:** `~/.claude/projects/*cs4-bench-policy-work-p{118,120,137,175,203,205}-{main,teach,outline}-r{1,2,3}/` (local).
- **#375's runs:** `devkb-benchmark-375-teach-archive.tar.gz` next to the checkout (local; the streams hold paths).
