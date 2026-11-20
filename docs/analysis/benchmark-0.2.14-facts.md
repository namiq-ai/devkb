# The 0.2.14 tickets as a benchmark: every fact, what is inferred, what is unknown (2026-11-19)

Purpose: a record for a reader who will re-examine devkb's design (a stronger model, or the owner). It lists what was
run, what was measured and how to reproduce each number, what the numbers do and do not show, and the defects found in
the benchmark itself and in my own handling of it. **Facts** carry a source. **Inferences** are marked *(inferred)*.
**Unknowns** are listed in section 9. Nothing is rounded in devkb's favour or against it.

How to reproduce every table: `python bench/policy/analysis_0214.py --runs <the run archive>` (standard library only). The
rows it reads are committed as `bench/policy/results-{301..307,331}.jsonl`. The run streams hold local paths, so they are
not committed: they are in an archive kept next to the repository (section 10).

## 1. What was run

- **Tickets (8):** #301-#307, the 0.2.14 measurement prerequisites (bugs in the benchmark harness itself), and #331 (the arms
  must run the same suite). All are small Python fixes in `bench/policy/` (solution sizes in section 2: two files, 11-41 lines
  inserted, except #331: five or six files).
- **Arms (2):** `none` = no devkb: the guardrail scripts, `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.mcp.json` are deleted, `Bash(devkb:*)`
  is denied, no graph. `main` = devkb CLI from the base commit: `CLAUDE.md` imports `AGENTS.md` (8.8 KB, the devkb policy),
  the PreToolUse guardrail hook is on (`DEVKB_GUARDRAIL=1`), graphs are built for the checkout. No MCP server in either arm.
- **Repetitions:** 3 per ticket and arm, 48 runs; one batch per ticket, shuffled, 6 in parallel. Model: `--model sonnet`
  (`claude-sonnet-5-5` in the stream's init event); Claude Code 2.1.329. Total cost of the 48 runs: $10.30 ($4.57 `none`, $5.73 `main`).
- **Run settings (`policybench._run_one`):** `--max-turns 150`, `--permission-mode acceptEdits`, `--setting-sources project,local`,
  `--strict-mcp-config` with an empty MCP config; allowed tools `storybench.ALLOW`, denied `storybench.DENY` (plus `Bash(devkb:*)` in `none`).
- **The prompt:** `policybench.PROMPT` + the ticket's title and body as filed. The prompt still says "The pinned C/C++ corpus
  repositories are in ./corpus/ (cJSON, leveldb, fmt)", which is irrelevant to these Python tickets *(inferred: a few
  hundred tokens and some confusion; not measured)*.
- **Scoring:** a hidden check per ticket (`bench/policy/accept/<N>.py`, black box, written from the ticket's Expected list, verified
  to fail on the ticket's base commit and pass on the fix) and the full test suite of the checkout.
- **Base commits:** #301 `4155904`; #302 `7b4a75e`; #303 `4b656e1`; #304 `ed60bac`; #305, #306, #307, #331 `2bb0c86`. The agents did not see
  the merged fixes. #301-#304 are a **backfill**: my own single-arm fix was written and merged first (PRs #323, #325, #326, #327);
  #305-#307 and #331 had their arms run before any fix was written (the fix of #305 is PR #332, of #331 PR #333; #306 and #307 are not yet fixed).
- **Harness version:** all 48 runs used the harness *before* #331 and #334. The `none` and `main` checkouts therefore ran
  **different test suites** (675 against 986 tests on #301's base; 694 against 1005 on #331's) and the Bash tool's 120 s default
  timeout applied. Both are defects of the benchmark (section 6). Results rows carry no test count and no first-call context
  (added by #331 for later runs).

## 2. Outcomes

| Ticket | Arm | Runs | Hidden check | Suite | Turns | Context k | Cost $ | Wall min | Solution size (distinct) |
|---|---|---|---|---|---|---|---|---|---|
| #301 | none | 3 | 3/3 | 3/3 | 11.0 | 319 | 0.16 | 2.3 | 2 files changed, 13 insertions(+); 2 files changed, 13 inser |
| #301 | main | 3 | 3/3 | 3/3 | 16.7 | 551 | 0.21 | 4.1 | 2 files changed, 13 insertions(+); 2 files changed, 16 inser |
| #302 | none | 3 | 1/3 | 3/3 | 13.3 | 429 | 0.20 | 4.0 | 3 files changed, 34 insertions(+), 3 deletions(-); 3 files c |
| #302 | main | 3 | 3/3 | 3/3 | 14.7 | 521 | 0.21 | 4.6 | 3 files changed, 34 insertions(+), 3 deletions(-); 3 files c |
| #303 | none | 3 | 3/3 | 3/3 | 8.7 | 263 | 0.18 | 2.2 | 2 files changed, 24 insertions(+), 1 deletion(-); 2 files ch |
| #303 | main | 3 | 3/3 | 3/3 | 16.7 | 605 | 0.25 | 3.5 | 2 files changed, 28 insertions(+), 3 deletions(-); 2 files c |
| #304 | none | 3 | 3/3 | 3/3 | 5.0 | 130 | 0.09 | 1.8 | 2 files changed, 11 insertions(+), 1 deletion(-); 2 files ch |
| #304 | main | 3 | 3/3 | 3/3 | 12.0 | 382 | 0.16 | 2.9 | 2 files changed, 11 insertions(+), 1 deletion(-); 2 files ch |
| #305 | none | 3 | 2/3 | 3/3 | 9.7 | 293 | 0.16 | 2.1 | 2 files changed, 41 insertions(+), 3 deletions(-); 2 files c |
| #305 | main | 3 | 3/3 | 3/3 | 15.0 | 518 | 0.20 | 9.6 | 2 files changed, 27 insertions(+), 3 deletions(-); 2 files c |
| #306 | none | 3 | 3/3 | 3/3 | 15.7 | 498 | 0.22 | 3.0 | 2 files changed, 32 insertions(+), 1 deletion(-); 2 files ch |
| #306 | main | 3 | 3/3 | 3/3 | 20.3 | 737 | 0.26 | 6.0 | 2 files changed, 41 insertions(+), 4 deletions(-); 2 files c |
| #307 | none | 3 | 3/3 | 3/3 | 13.7 | 452 | 0.19 | 3.3 | 2 files changed, 22 insertions(+), 1 deletion(-); 2 files ch |
| #307 | main | 3 | 3/3 | 3/3 | 14.0 | 501 | 0.20 | 10.4 | 2 files changed, 19 insertions(+), 1 deletion(-); 2 files ch |
| #331 | none | 3 | 3/3 | 3/3 | 12.7 | 517 | 0.31 | 2.8 | 5 files changed, 106 insertions(+), 19 deletions(-); 5 files |
| #331 | main | 3 | 3/3 | 3/3 | 23.0 | 1144 | 0.42 | 4.6 | 5 files changed, 70 insertions(+), 14 deletions(-); 6 files  |

### Totals over the 8 tickets (24 runs per arm)

| Arm | Runs | Hidden check | Suite | Turns | Model calls | Context k | Output k | Cost $ | Wall mean min | Wall median min |
|---|---|---|---|---|---|---|---|---|---|---|
| none | 24 | 21/24 | 24/24 | 11.2 | 11.2 | 363 | 5.7 | 0.190 | 2.7 | 2.3 |
| main | 24 | 24/24 | 24/24 | 16.5 | 16.5 | 620 | 5.9 | 0.239 | 5.7 | 3.7 |

Hidden-check failures: p302-none-r1 (a_real_devkb_edit_still_counts); p302-none-r3 (a_real_devkb_edit_still_counts); p305-none-r1 (a_red_base_is_still_recorded)

### Facts from the tables above
- All 48 runs passed the full suite. The hidden check failed in 3 `none` runs and in no `main` run (21/24 against 24/24).
  The three failures are regressions the agent introduced, not misses: #302 `none` r1 and r3 broke "a real devkb edit still counts"
  (their rewritten edit rule stopped counting edits of devkb code), #305 `none` r1 broke "a red base is still recorded".
  *(inferred)* with devkb used 0 times, this is chance at n=3 or an effect of the policy text in the `main` prompt; it cannot be
  attributed to the graph. An earlier message of mine said "23 of 24"; the correct count is 21 of 24.
- The devkb arm used on average 16.5 turns against 11.2, 620k context against 363k, $0.239 against $0.190 per run (+26% cost, +71%
  context); output tokens were equal (5.9k against 5.7k). Wall time mean 5.7 against 2.7 min (median 3.7 against 2.3).
- Wall-time outliers: `p305-main-r3` and `p307-main-r2` took 22.6 min. Cause (from the streams): the suite was backgrounded at 120 s,
  then the agent wrote an `until grep ... passed` wait loop that ran to its own 600 s timeout, twice (gaps of 601 s and 593 s;
  592 s and 600 s in the other). Each wait loop ran to its own 600 s timeout (*inferred*: its condition never matched; the cause of that was not examined). The pattern is possible because of the cliff in section 4.

## 3. Use of devkb by the agents

| Arm | Runs | Bash commands | Bash invoking devkb | MCP devkb calls | Sum of devkb_nav | Sum of devkb_queries |
|---|---|---|---|---|---|---|
| none | 24 | 241 | 0 | 0 | 0 | 0 |
| main | 24 | 304 | 0 | 0 | 0 | 0 |

First tool of each devkb-arm run: {'Bash': 20, 'Read': 3, 'Grep': 1}

## 4. Where the extra turns and context went

| Category | none | main (devkb) | Difference |
|---|---|---|---|
| edit/write | 2.6 | 1.9 | -0.7 |
| git | 2.0 | 2.1 | +0.0 |
| other | 0.0 | 0.2 | +0.2 |
| reading/searching code | 3.8 | 4.7 | +0.9 |
| retry after a denied command | 3.2 | 2.6 | -0.5 |
| running tests | 1.8 | 2.7 | +0.8 |
| waiting on a background run | 0.0 | 2.8 | +2.8 |
| **total tool calls** | 13.5 | 17.0 | +3.5 |

### The 120-second default and the suite's duration

| Arm | Runs with a command backgrounded by the default | Commands backgrounded | pytest calls | pytest calls that set their own timeout | Full-suite commands that ran (n) | Median s | Mean s | Max s |
|---|---|---|---|---|---|---|---|---|
| none | 0/24 | 0 | 81 | 1 | 21 | 97 | 97 | 101 |
| main | 24/24 | 24 | 102 | 14 | 20 | 120 | 179 | 601 |

### Starting context

| Arm | First-call context, mean tokens | min | max |
|---|---|---|---|
| none | 23591 | 23261 | 23882 |
| main | 27090 | 26526 | 27777 |

### Permission denials and the missing reproduction data

| Arm | Permission-denied events in the stream | per run | Tool results that are denials | per run | Calls aimed at the audit data (#301-#307) | Final reports saying a reproduction could not be run (#301-#307) |
|---|---|---|---|---|---|---|
| none | 89 | 3.7 | 76 | 3.2 | 72 (3.4/run) | 21/21 |
| main | 74 | 3.1 | 63 | 2.6 | 41 (2.0/run) | 21/21 |

## 5. The hook

Log rows for the 24 devkb-arm runs: 57; runs with no row: ['p301-main-r3']

By action: {'pass-through': 32, 'remind': 21, 'alongside': 4}
Pass-through reasons: {'duplicate:in-file': 1, 'duplicate:call-sites': 2, 'not-complete': 20, 'intent:list-files': 3, 'stale-graph': 1, 'intent:count': 3, 'duplicate:read-body': 2}
Pass-through verdicts: {'complete': 13, 'cannot-resolve': 12, 'no-match': 17, 'other-case': 1}
Pass-through characters sent to the agent: 0
Reminder intents: {'in-file': 1, 'call-sites': 4, 'locate': 6, 'list-files': 1, 'literal': 7, 'read-body': 2}
Answers beside grep (alongside): [('p304-main-r2', ['devkb_selftest', 'devkb_nav'], 393), ('p304-main-r3', ['devkb_selftest', 'devkb_nav'], 393), ('p331-main-r3', ['nonekeep'], 275), ('p331-main-r1', ['ctx_tokens'], 346)]


## 6. Defects found in the benchmark itself (open or fixed; the numbers above were measured with them present)

| # | Defect | Evidence | Where tracked |
|---|---|---|---|
| D1 | The arms ran different suites: `none` deletes the guardrail's tests and their dependents (675 tests), `main` keeps them (986). The full suite is what both agents run to check their work | collected counts on #301's checkouts 675 vs 986; on #331's base 694 vs 1005 | fixed by #333 (all arms trimmed; test count and first-call context now printed; template key includes the setting). The 48 runs here predate it |
| D2 | The Bash tool backgrounds a command after 120 s. The `none` suite took median 97 s (max 101 s), the `main` suite median 120 s (mean 179 s, max 601 s) | 24/24 `main` runs and 0/24 `none` runs had a backgrounded command; waiting calls 0.0 against 2.8 per run (80% of the +3.5 tool calls); experiment: a 125 s command is backgrounded by default and finishes in one call with `BASH_DEFAULT_TIMEOUT_MS=300000` | #334 |
| D3 | `.venv/bin/devkb`, the command the checkout's policy prescribes, is not in the allowlist | experiment with the benchmark's exact flags: denied ("requires approval"), `devkb` runs. 0 of 304 `main` Bash commands tried either form, so it did not change these results | #335 |
| D4 | The tickets' reproduction data (`bench/results/2026-11-19-audit-0.2.13/`) is in no merged branch | 0 tracked files; 72 (`none`, 3.4 per run) and 41 (`main`, 2.0 per run) calls aimed at it; 21/21 final reports of #301-#307 say it could not be run | #336 |
| D5 | The hook's output is not in the run stream, so "the agent saw the reminder" cannot be shown | the stream has no hook events; the claude CLI has `--include-hook-events` (not used) | #330 |
| D6 | The first reminder is sent for a literal, anchored grep, which its own text says is grep's job | 7 of the 21 reminders (33%) were for intent `literal` | #329 |
| D7 | Permission-checker denials cost retries in both arms | 89 (`none`) and 74 (`main`) permission-denied events in 24 runs each (3.7 and 3.1 per run); causes: variables, brace expansion, compound commands | not filed; both arms alike |
| D8 | Results rows scored before #331 have no test count or first-call context | rows lack `tests_collected`, `first_ctx` | the table prints "unknown" for them |
| D9 | The prompt mentions the C/C++ corpus, irrelevant to these tickets | `policybench.PROMPT` | not filed |
| D10 | n=3 per arm per ticket; one model; one repository (devkb itself, about 60 modules) | the design | section 9 |
| D11 | **The agents' checkouts live inside the repository that holds the harness** (`bench/policy/work/<run>`), so a cut-down absolute path reaches the harness's own source. 26 tool calls in 11 runs named a path in the real repository outside the run's own checkout; **3 runs wrote to it** (`p301-main-r1`, `p306-none-r1`, `p307-none-r1`). `p306-none-r1` edited `policybench.py` and a test there, ran `git -C <real repo> diff`, noticed, and redid the work in its checkout, leaving its edits behind (found afterwards as uncommitted changes in the working tree; saved, then discarded). No tool call read a hidden check or another run's data (all 48 streams checked) | the Edit/Write calls above; archive `devkb-benchmark-0.2.14-contamination.tar.gz` (the leftover diff and a test file) | #340 |

## 7. What the runs say about devkb's design

Facts first, then the reading. Prior evidence is in `docs/analysis/bugfix-benchmark.md` (138 runs, 2026-11-18) and
`docs/analysis/devkb-none-mcp-cli.md`; the new runs agree with it and add rows to it.

1. **The agents never used devkb on these tickets.** 0 of 304 Bash commands in the `main` arm invoked devkb; `devkb_nav` is 0 in all
   24 runs; the first tool call of every one of the 24 runs was a direct read or grep of the file the ticket names (20 Bash, 3 Read, 1 Grep), for example `sed -n 270,330p policybench.py` for
   a ticket whose "Where to start" says L290-309. Earlier benchmark: devkb used in 8 of 84 runs where offered (bugfix-benchmark.md). **Fact.**
2. **The task never needed navigation, by construction.** 32 of the 33 open 0.2.14 tickets name a file, line or symbol under "Where to start"
   (the ticket standard, `CLAUDE.md` rule 3, requires it). The graph's job is "where is this, who calls it, what tests reach it". **Fact:**
   the standard and the tickets. *(inferred)*: any benchmark made of tickets written to that standard has the location handed over.
3. **Removing the location did not bring devkb into use in the earlier tests.** Variant B (no "Where to start"): devkb queried in 1 of 12 runs;
   T1 (symptom-only tickets): 1 of 12 plus 1 of 12 with the hook. Agents grepped for the subsystem or the repro's words and landed on the code.
   **Fact (earlier document).** So the ticket I filed as #337 ("benchmark tickets that do not say where to start") would, on that evidence, not change
   devkb's use by itself; the same document concludes the graph's measured value is on impact and chain questions, and audits (31-39% of navigation calls;
   -37% median cost on C/C++ chain questions when asked). I have revised #337 to say so.
4. **The policy is advice, and advice is not followed at the point of need.** The checkout's `AGENTS.md` says "ask the graph before you read or change code"
   and tells agents which command to run; 0 of 24 runs did. The hook reminds once per session (21 reminders in 24 runs) and the reminder arrived after the agent
   already held the file *(inferred from the run order in p302-main-r1; the log has no command text)*. **Fact:** 0 devkb queries after 21 reminders.
5. **The hook answers rarely.** 57 decisions in 24 runs: 21 reminders (37%), 32 pass-throughs (56%), 4 answers beside grep (7%). Of the 32 pass-throughs, 20 were
   `not-complete`, 5 `duplicate:*` (the name has several definitions), 1 `stale-graph`, 6 out-of-scope intents (file listings, counts); verdicts `no-match` 17,
   `cannot-resolve` 12, `complete` 13, `other-case` 1. 0 characters reached the agent from the 32. The 4 answers were for string keys (`devkb_selftest`,
   `devkb_nav`, `nonekeep`, `ctx_tokens`), i.e. names with no symbol of that name. **Fact.** *(inferred)* in this repository the graph often cannot give a
   complete answer for the names an agent greps: common words and names shared by many symbols (a pack on `run_suite` was Incomplete: 9 symbols share the name).
6. **Offering devkb costs context even when unused.** First-call context 23.6k (`none`) against 27.1k (`main`): +3.5k tokens (+15%) in the very first call,
   carried in every later call. The extra turns and the rest of the context gap come from the 120 s cliff and the unequal suite (D1, D2), not from devkb queries.
   **Fact** for the first-call figure; the split of the context gap is arithmetic on the table: over all 48 runs the gap is 257k (620k against 363k); the extra 5.3 calls at the devkb arm's 37.6k average call explain 199k (77%), and the larger average call (37.6k against 32.4k) over the `none` arm's 11.2 calls explains 58k (23%). On #301-#304 alone the split was 83% and 17%.
7. **The graph is built at the base commit and agents edit the code.** One pass-through was `stale-graph`; a `pack` run during this work printed "graph stale:
   built at ..., repository is N commits ahead". No agent ran `devkb build` (0 devkb commands). *(inferred)* an edit session makes the graph stale within minutes
   unless the tool rebuilds; this was not measured directly.
8. **devkb is delivered as CLI plus policy text, by decision.** MCP was dropped because its 12 tool definitions cost about 3k tokens on every call
   (`devkb-none-mcp-cli.md`). The same document found agents "chose the shell anyway" where MCP was available; here the shell form was never chosen either.

## 8. What I did wrong in this work (so a reader can discount it)

- I wrote and merged the fixes of #301-#304 first, single-arm, with single-arm reviews posted as plain comments; the two-arm backfill came after the owner asked.
  The reviews of every PR here were by one reviewer (me), not the with-and-without-`review_pack` pair #316 specifies; the gate (`bench/review/gate.py`) is real, the
  findings files I fed it were written by me.
- #303 was first cut from a stale `origin/main` and collided with #302's merge; the first version of the gate (#324) failed open on an unknown severity
  and on draft PRs (found in review, fixed before merge); my #331 code crashed the release table on older rows (caught by the full suite); my template key
  for #331 lacked the suite setting (the #307 bug class, caught in audit). All fixed before merge.
- I reported "23 of 24" for the hidden checks (it is 21 of 24), and my script first counted 24 of 24 reports saying a reproduction could not be run because it included
  #331, which has no such reproduction (21 of 21 for #301-#307 is right). Both corrected.
- My first explanation of the extra turns (policy text, more verification) was a guess; the data say the 120 s cliff and the suite size. I named hypotheses as such,
  but I presented the +30% cost / +80% context figures before I had found that cause; they should not be quoted as devkb's overhead.
- I ran the benchmark with the agents' checkouts inside my own working repository and left that repository's working tree where an agent's stray edit could change the harness for the next batch (D11). I found it only while preparing a clean tree. The later batches (#307, #331) imported `policybench.py` after `p306-none-r1`'s edit had been left in it; the edit touched only `score()` (which rows the results file keeps), so I do not expect a different outcome *(inferred; not re-run)*.
- I asked the owner questions that I could have answered by testing (the allowlist, the timeout); the later experiments did that.

## 9. Unknowns, and what to explore next

1. **Whether the agents saw the reminder text, and what they made of it.** The stream has no hook output (#330) and no reasoning text, only thinking-token counts.
   *Try:* run with `--include-hook-events` and compare the next action after each reminder.
2. **The size of devkb's own overhead once D1 and D2 are removed.** *Try:* re-run these 8 tickets with equal suites and a raised Bash timeout (#334); the
   difference left is the policy text, the hook and the graph, and nothing else.
3. **Whether any variant makes agents ask the graph on tickets like these.** The repository has an `outline` arm (first-open outline) and `noteach`; neither was run
   here. *Try:* a first-turn injection of `devkb outline` for the named file, a policy cut to a few lines, and a prompt that names the question to ask
   ("before changing X, list everything that calls or computes X").
4. **Impact tickets.** The earlier T3 (cross-file renames) saw 0 devkb use in 12 runs because Python call sites are qualified and the suite catches misses.
   *Try:* tickets whose fix needs the callers of a function in 3+ files and whose test suite does not cover the callers (candidates open now: #286, #290, #289, #244; hidden check per ticket).
5. **Variance and other models.** n=3; Sonnet only. The same ticket varied 1.5-2x in cost between two runs in the earlier document.
6. **Graph quality on this repository.** 20 of 32 pass-throughs were "not complete". *Try:* for the names the hook failed on, `devkb symbol`/`pack` by hand and
   record why: duplicates, string keys, generic words, stale graph.
7. **The guardrail's PostToolUse miss log** (`devkb misses`) listed 4 groups (`counts`, `root`, `devkb_commands`, `edits_devkb_code`): two generic names, one stale-graph case, one
   incomplete pack; none filed.
8. **Cost accounting.** Cost is the CLI's reported cost; the share of cache reads against fresh input in the +229k context was not separated.
9. **Timing of the two suites side by side** was not measured directly (only the agents' own runs: 97 s against 120 s median); #334's work will time them.

## 10. Data and records

- Result rows: `bench/policy/results-301.jsonl` ... `results-307.jsonl`, `results-331.jsonl` (6 rows each). Tables: `bench/policy/analysis_0214.py`.
- Run streams, hook log slice, and the raw tables: archive `devkb-benchmark-0.2.14-archive.tar.gz` kept next to the repository checkout (1.3 MB compressed, 7.6 MB of streams; not committed because the streams hold local paths). It also holds the 57 hook-log rows of these runs, the committed result rows and the generated tables.
- Hidden checks: `bench/policy/accept/301.py` ... `307.py`, `331.py`. Checklist: `AGENTS.md`, "Per-ticket checklist".
- Tickets fixed and merged: #301 (PR #323), #302 (#325), #303 (#326), #304 (#327), #305 (#332), #331 (#333); open: #306, #307. Gate: PR #324 (part 1 of #316); checklist and checks: PR #328.
- Issues from this work: #339 (0.2.15 epic: efficiency and performance), #340 (D11), #329 (reminder on literal grep), #330 (hook output in the stream), #334 (120 s timeout), #335 (`.venv/bin/devkb` allowance), #336 (reproduction data),
  #337 (milestone 0.2.15: tickets that need navigation, revised), #331 (equal suites, done).

## Appendix A. Per run

| Run | Wall min | Turns | Model calls | Context k | Cost $ | Hidden | Suite | Hook actions |
|---|---|---|---|---|---|---|---|---|
| p301-main-r1 | 5.6 | 14 | 14 | 450 | 0.18 | pass | pass | {"pass-through": 1, "remind": 1} |
| p301-main-r2 | 3.4 | 18 | 18 | 611 | 0.23 | pass | pass | {"pass-through": 2, "remind": 1} |
| p301-main-r3 | 3.2 | 18 | 18 | 593 | 0.21 | pass | pass | {} |
| p301-none-r1 | 2.3 | 11 | 11 | 316 | 0.16 | pass | pass | {} |
| p301-none-r2 | 2.3 | 13 | 13 | 382 | 0.17 | pass | pass | {} |
| p301-none-r3 | 2.3 | 9 | 9 | 260 | 0.16 | pass | pass | {} |
| p302-main-r1 | 3.2 | 11 | 11 | 377 | 0.19 | pass | pass | {"remind": 1, "pass-through": 1} |
| p302-main-r2 | 5.3 | 19 | 19 | 695 | 0.24 | pass | pass | {"pass-through": 1, "remind": 1} |
| p302-main-r3 | 5.2 | 14 | 14 | 493 | 0.20 | pass | pass | {"remind": 1} |
| p302-none-r1 | 3.9 | 12 | 12 | 376 | 0.17 | FAIL | pass | {} |
| p302-none-r2 | 4.3 | 17 | 17 | 572 | 0.28 | pass | pass | {} |
| p302-none-r3 | 3.9 | 11 | 11 | 341 | 0.17 | FAIL | pass | {} |
| p303-main-r1 | 3.6 | 12 | 12 | 420 | 0.24 | pass | pass | {"pass-through": 2, "remind": 1} |
| p303-main-r2 | 3.5 | 17 | 17 | 654 | 0.27 | pass | pass | {"pass-through": 3, "remind": 1} |
| p303-main-r3 | 3.4 | 21 | 21 | 742 | 0.25 | pass | pass | {"pass-through": 1, "remind": 1} |
| p303-none-r1 | 2.2 | 8 | 8 | 239 | 0.17 | pass | pass | {} |
| p303-none-r2 | 2.4 | 9 | 9 | 291 | 0.20 | pass | pass | {} |
| p303-none-r3 | 2.2 | 9 | 9 | 260 | 0.16 | pass | pass | {} |
| p304-main-r1 | 2.8 | 12 | 12 | 369 | 0.14 | pass | pass | {"remind": 1} |
| p304-main-r2 | 2.9 | 8 | 8 | 245 | 0.13 | pass | pass | {"alongside": 1} |
| p304-main-r3 | 3.0 | 16 | 16 | 532 | 0.19 | pass | pass | {"alongside": 1} |
| p304-none-r1 | 1.9 | 5 | 5 | 131 | 0.09 | pass | pass | {} |
| p304-none-r2 | 1.8 | 5 | 5 | 131 | 0.09 | pass | pass | {} |
| p304-none-r3 | 1.8 | 5 | 5 | 130 | 0.09 | pass | pass | {} |
| p305-main-r1 | 3.2 | 12 | 12 | 388 | 0.17 | pass | pass | {"pass-through": 1, "remind": 1} |
| p305-main-r2 | 3.0 | 17 | 17 | 596 | 0.21 | pass | pass | {"remind": 1} |
| p305-main-r3 | 22.6 | 16 | 16 | 569 | 0.23 | pass | pass | {"remind": 1, "pass-through": 3} |
| p305-none-r1 | 2.2 | 10 | 10 | 323 | 0.19 | FAIL | pass | {} |
| p305-none-r2 | 2.1 | 9 | 9 | 260 | 0.13 | pass | pass | {} |
| p305-none-r3 | 2.1 | 10 | 10 | 297 | 0.16 | pass | pass | {} |
| p306-main-r1 | 6.3 | 31 | 31 | 1181 | 0.33 | pass | pass | {"remind": 1, "pass-through": 2} |
| p306-main-r2 | 5.6 | 11 | 11 | 349 | 0.18 | pass | pass | {"remind": 1} |
| p306-main-r3 | 6.2 | 19 | 19 | 682 | 0.25 | pass | pass | {"remind": 1, "pass-through": 1} |
| p306-none-r1 | 4.3 | 22 | 22 | 753 | 0.28 | pass | pass | {} |
| p306-none-r2 | 2.4 | 15 | 15 | 442 | 0.19 | pass | pass | {} |
| p306-none-r3 | 2.3 | 10 | 10 | 299 | 0.18 | pass | pass | {} |
| p307-main-r1 | 5.2 | 14 | 14 | 499 | 0.20 | pass | pass | {"pass-through": 2, "remind": 1} |
| p307-main-r2 | 22.6 | 16 | 16 | 593 | 0.23 | pass | pass | {"pass-through": 2, "remind": 1} |
| p307-main-r3 | 3.4 | 12 | 12 | 411 | 0.18 | pass | pass | {"pass-through": 1, "remind": 1} |
| p307-none-r1 | 4.0 | 18 | 18 | 644 | 0.25 | pass | pass | {} |
| p307-none-r2 | 3.7 | 8 | 8 | 231 | 0.12 | pass | pass | {} |
| p307-none-r3 | 2.3 | 15 | 15 | 480 | 0.21 | pass | pass | {} |
| p331-main-r1 | 5.8 | 13 | 13 | 568 | 0.31 | pass | pass | {"pass-through": 2, "remind": 1, "alongside": 1} |
| p331-main-r2 | 3.9 | 28 | 28 | 1354 | 0.44 | pass | pass | {"remind": 1, "pass-through": 4} |
| p331-main-r3 | 4.0 | 28 | 28 | 1510 | 0.51 | pass | pass | {"alongside": 1, "pass-through": 3, "remind": 1} |
| p331-none-r1 | 3.1 | 13 | 13 | 582 | 0.38 | pass | pass | {} |
| p331-none-r2 | 2.5 | 13 | 13 | 497 | 0.27 | pass | pass | {} |
| p331-none-r3 | 2.7 | 12 | 12 | 471 | 0.29 | pass | pass | {} |
