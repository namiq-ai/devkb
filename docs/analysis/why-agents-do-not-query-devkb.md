# Why agents given devkb do not query it (#381, 2026-11-20)

**Question.** Agents given devkb (its policy in `AGENTS.md`, the guardrail hook, a built graph) almost never run a devkb query. In 0.2.14, the epic's summary counts 0 of 45 devkb-arm runs (#339; the performance report's "0 of 38" was counted before the last 7). In the 63 devkb-arm runs since, on #372, #371, #375 and #375's keep-or-drop benchmark, it is again 0, checked in every stream. Each lever tried so far was measured on its own and none moved it. This document puts the evidence together and ranks the causes. **Facts** have a source; *(inferred)* marks a reading.

**How a query is counted.** A command counts only when a shell segment *starts* with a devkb query (`devkb symbol|outline|uses|docs|pack|query|misses`, or a path ending in `devkb`). Not counted: devkb text inside a heredoc edit, and `devkb` as a path argument of `grep` (for example `grep -r X devkb docs/`). The harness's own counter counts both (#309), and this document's first version matched the second.

**Data.**
- **0.2.13:** the transcripts of the `main`, `teach` and `outline` runs on the six D1 tickets (#118, #120, #137, #175, #203, #205), in `~/.claude/projects/*cs4-bench-policy-work-p<ticket>-<arm>-r<n>/<session>.jsonl` (local), with the result rows in `bench/results/2026-11-19-release-0.2.13/results/`.
- **Since 0.2.14:** the run streams of #372, #371 and #375 and #375's benchmark (`devkb-benchmark-375-teach-archive.tar.gz`, next to the checkout).
- **81 interviews:** `bench/policy/interviews-381/answers.jsonl`.

## 1. The answer, ranked

| # | Cause | Verdict | Evidence |
|---|---|---|---|
| 1 | **The ticket hands over the location, so a read is the shortest path** | **supported, confounded** (#337 decides it) | 0 of 63 runs since 0.2.14 tried devkb, all on tickets that give line numbers, against 16 of 54 on 0.2.13's tickets, 5 of 6 of which give none (Fisher p ≈ 1e-6). 58 of 63 agents asked "why not" named the ticket's location. The sets also differ in tickets, code areas, devkb versions and permission rules (section 3). |
| 2 | **When agents did try, the benchmark refused the command** | **confirmed**, for 0.2.13 | 35 attempts in 16 runs; **all 35 refused** by the permission checker, **0 answered** (19 compound commands, 15 needing approval, 1 an unchecked variable). 15 of the 18 interviewed agents said so. |
| 3 | **Advice at the point of need is not followed** | **confirmed** | The teach line was seen 17 times in #375's `teachall` arm, with 0 queries. 35 of 63 agents said a hook or guardrail hint was shown and they did not act on it. |
| 4 | **The work is small and local, so the expected gain is small** | **reported**, consistent with the data | 32-36 of 63 called the fix small or local. Almost all (about 60 of 63) judged devkb would have helped "a little" or "somewhat", at most 2 "not at all" (both also say "a little"), **none "clearly"**. |
| 5 | Familiarity: grep and sed are free to recall, devkb is an unknown CLI | **open** | 6 of 63 said "habit" or "momentum". Not tested by an arm (SPEC-DKB-007 D3, intent-named native tools, was never built). |
| 6 | The model | **open** | Only Sonnet 5.5 has been measured. |

**Not a cause, but a defect found on the way:** devkb's "tests to run" for the bench files these tickets change lists 0-1 tests, against 1-11 test files that load them (#382). The cause is that the tests bind the module to a short alias (`sb = importlib.import_module("storybench")`). Agents name "tests to run" as devkb's main value. But no agent since 0.2.13 got a devkb answer at all, so this defect cannot have put anyone off. It matters for the next measurement, not for this one.

## 2. The 0.2.13 positive case was refused commands, not answers

0.2.13's D1 decision (#218) recorded 1.50 direct queries a run with the teach line against 0.17 without it, and turned the line on by default (#267). The transcripts show otherwise:

- **The first user message is byte-identical** across `main`, `teach` and `outline` for each ticket (sha1 checked for #118, #120, #203).
- **Every attempt was refused:** 35 attempts in 16 runs, and no tool result without an error.
- **The teach line came after the first attempt in all 9 `teach` runs that tried** (the first attempt at tool call 1 or 2; the teach line, where it came at all, at call 4-10). It cannot have caused those attempts.
- In 3 of those 9 runs the guardrail's generic **reminder** ("ask devkb first (`devkb symbol|uses|outline|pack …`)") arrived at call 1, before the first attempt at call 2. The `main` arm got the same reminder.

| Ticket | main: first devkb attempt at tool call | teach | outline |
|---|---|---|---|
| #118 | none, none, none | 2, 1, none | none, none, none |
| #120 | none, none, 3 | 1, 2, 2 | 1, 1, none |
| #137 | 13, none, none | none, none, 1 | none, none, 1 |
| #175 | none, none, none | none, none, 1 | none, none, none |
| #203 | 3, none, none | 1, 2, none | none, none, none |
| #205 | none, none, none | none, none, none | 1, none, none |

**Runs that tried:** main 3 of 18, teach 9 of 18, outline 4 of 18 (16 of 54). Teach against main: two-sided Fisher exact **p = 0.075**.

**Reading.** The policy text (`AGENTS.md`), together with the guardrail's reminder (which every arm had, so they cannot be separated), brought agents to devkb at the start of these tickets, and the benchmark refused them every time. The teach line was not the trigger: in every run that tried, it appeared later. The gap between `teach` and `main` (9 against 3, p = 0.075) is not explained by the line, and with byte-identical prompts it is most likely run-to-run variation *(inferred)*. #375's direct test (17 teach lines seen against 7, 0 queries in both arms) agrees. D1 is still on by default for the answers the hook gives (#267). Whether to keep it is the owner's decision; this document records that the measurement it was based on does not show what #218 read in it.

## 3. The ticket's shape

| Set | Line numbers in "Where to start" | Files named, and their size when the agents worked | Runs that tried devkb |
|---|---|---|---|
| 0.2.13's six D1 tickets (base 28a77c9) | 1 of 6 (#118) | `cpp_symbols.py` 1,162, `scripts/devkb_guardrail.py` 1,173, `ops/triage/triage.py` 757, `read_tools.py` 747, `misses.py` 394, `cpp_resolve.py` 373, `cpp_graph.py` 290; classes and functions by name | **16 of 54** |
| #372, #371, #375 and the nine tickets of #375's benchmark | all (`L290-309`, `L131-136`, `~L1399`, …) | bench files of 222-478 lines, and also `read_tools.py` 775, `devkb_guardrail.py` 1,481, `tests/test_csharp_symbols.py` 1,254 | **0 of 63** |

**File size does not separate the two sets; the line numbers do.** The later tickets touch files as large as 0.2.13's. Fisher exact p ≈ 1e-6 for 16 of 54 against 0 of 63.

**Confounded:** different tickets and code areas, different devkb versions, and the permission fixes of #334 and #335 between the sets. The permission fixes would have turned refusals into answers. They cannot explain why the later set made no *attempts*, but other differences may *(inferred)*. *(inferred)*: with a line range the agent runs `sed -n A,Bp` straight away; with only a name, it has a navigation step, and that is where the 0.2.13 agents ran `devkb outline` or `pack`. #337's design (the same tickets with and without the location) separates the ticket's shape from the rest.

## 4. What agents say (81 interviews)

**Method.** Each finished session was resumed once (`claude -p --resume <session>`), in its own checkout, with no tools allowed and one turn, and asked one fixed question:
- **Runs that did not query devkb (63):** "You were working on this ticket in a repository that offered devkb (its AGENTS.md describes it; a hook may have shown a devkb command). You did not run devkb. In two or three sentences, why not? Name what you used instead and whether devkb would have helped. Answer in text only."
- **0.2.13 runs flagged as having tried (18):** "You ran devkb during this ticket. In two or three sentences: what made you reach for it at that point, instead of grep or reading the file? Did its answer help, and would you use it again for this kind of task?" Two of these 18 had not run devkb (the `grep … devkb docs/` false positive above), and both said so.

Cost: $30.81 for 81 sessions ($2.30 for a pilot of 9; about $0.25 for a "why not" session, more for the larger 0.2.13 sessions).

**Limits.** The answers are reconstructed after the fact, and agents lean towards self-blame against `AGENTS.md` ("that was a lapse on my part"). So a claim here counts only when the run data agrees. Counts are a full reading of the 63 answers by one reviewer, cross-checked by keyword rules. Where the two differ, both are given. An answer can fall into several groups. The first version of this document used looser rules and miscounted two groups (15 against 35 for the hook hint; 17 against at most 2 for "would not have helped").

| "Why not" (63 answers) | Answers |
|---|---|
| The ticket named the file, function or lines | 58-59 |
| A hook or guardrail hint was shown and the agent did not act on it | 35 |
| The fix was small or local | 32-36 |
| Habit or momentum | 6 |
| devkb would have helped "a little / somewhat" / "not at all" / "clearly" | about 60 / at most 2 / 0 |

| "What made you reach for it" (18 answers, 0.2.13) | Answers |
|---|---|
| `AGENTS.md` says to ask the graph first | 11 |
| The command was refused | 15 |
| Never ran a query (only the hook's output, or devkb's build) | 3 |

**Checked against the data:**
- #302's agent said devkb would have shown `test_bench_run_measures_258.py` "before my first full run failed on it". The stream confirms the failure (`1 failed, 686 passed`, then a fix and a rerun).
- `devkb pack file bench/policy/storybench.py` at that base lists 0 tests, so devkb would not have named it (#382). Renaming the test's `sb` alias to `storybench` makes the pack list it, which confirms the cause.

## 5. What follows

- **#337, tickets without the location**, is the experiment that decides cause 1. Run it before any further change to the policy text or the hook.
- **#369 (permission denials) and #379 (the MCP config race):** a refused or broken command is how every one of 0.2.13's real attempts ended.
- **#382 (aliased imports in tests)** has to land before a benchmark can credit devkb with the "tests to run" value agents name.
- **D3 (intent-named native tools)** is the untested candidate for cause 5; **a second model** on the same nine tickets tests cause 6.
- **D1's default (#267)** rests on the 0.2.13 figures in section 2. Keeping it is the owner's call.

## 6. Data

- **Interviews:** `bench/policy/interviews-381/answers.jsonl` (run, question, answer and cost; paths redacted, no session ids).
- **0.2.13 transcripts:** `~/.claude/projects/*cs4-bench-policy-work-p{118,120,137,175,203,205}-{main,teach,outline}-r{1,2,3}/` (local).
- **#375's runs:** `devkb-benchmark-375-teach-archive.tar.gz` next to the checkout (local; the streams hold paths). Its cost figure (+12.6%) is the geometric mean of the nine per-ticket cost ratios; the ratio of total costs is +12.1%.
