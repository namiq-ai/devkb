# Where the hooks can be improved: evidence per row, and what the guide adds (2026-11-23)

Evidence: the guard log (2,111 decisions since the v0.2.14 tag, all sessions on this machine), 4 working-session transcripts, a replay of the pre-edit hook's own code over them, and today's graph. Scripts: `/home/namiq/.claude/jobs/d417ed39/tmp/{names_symbol,replay_preedit2,compact_sim}.py` (to be moved to `bench/audit/` under the ticket that uses them). Every number says its population. Nothing here has been run against an agent: each item is sized by replay and proposes the check that would settle it.

## 1. Findings that change what 0.2.16 should do

| # | Finding | Evidence |
|---|---|---|
| F1 | **`not-complete` is mostly not a graph-quality problem.** 599 decisions (28%) were withheld as `not-complete`; their 541 `cannot-resolve` name verdicts split: **52% (280) have no exact symbol at all** (plain words such as `scope`, `extract`, `decide`; variables; constants), **43% (234) have an exact symbol in several places** (`pack refactor` refuses an ambiguous name), **4% (22) have exactly one**, 1% none. | `names_symbol.json` over the log's `names` and `verdicts`, checked with `devkb symbol` on today's graph (a name's definitions may have changed since it was logged) |
| F2 | **The hook asks one question for every intent.** All 599 `not-complete` decisions asked `pack refactor`, including `locate` (129 of 245 locate decisions withheld) and `read-body` (127 of 476). Finding a definition or reading its body does not depend on how complete the call graph is; the answer needed is `symbol` or `symbol --source`. | question column of the log; intent x outcome matrix (§3) |
| F3 | **One unresolved name withholds the whole search.** 144 of the 599 had at least one name that resolved Complete. 8 got a partial answer (`alongside:partial`). | `verdicts` field |
| F4 | **The 6,000-character cut removes the Incomplete note.** In the pre-edit hook the pack's Incomplete/Coverage warning is the last section; of the 17 packs over the cap (of 202 distinct files), **15 lose it**. The agent then reads a truncated pack that no longer says it is a lower bound. 98 of the 202 packs carry that note. | `compact_sim.py` on the real packs |
| F5 | **The tests section is 52% to 70% of a large pack** (5,210 of 7,402 characters for `cpp_resolve.py`; 7,084 of 13,684 for `build_symbols.py`) and carries the least decision value per character. | `devkb pack file` section sizes |
| F6 | **Pre-edit on `Bash` is the only high-volume path, and half of it is on reads.** Replayed over 4 sessions: 304 packs, 641k characters (about 160k tokens); 157 on commands that write (251k characters), 147 on commands that only read (390k). **74% of the injected files were changed later in the same session**, so the file choice is good; whether the pack changed what the agent did is unmeasured. | `replay_preedit2.py`; "write" is a regex over the command, approximate |
| F7 | **`stale-graph` collapsed after #410**: 9% of decisions on 11-20, 57% on 11-21, 1% (3 of 207) after #410 merged at 11-22 15:46. The last figure is mostly benchmark probes, thin evidence. By repository class before that: this repo's working sessions 15%, benchmark checkouts 26%, other repositories 45%. | log by day and by repository class |
| F8 | **Reminders are not worth optimizing**: once per session (median 1, max 2, in 414 of 431 sessions), 389 characters (about 100 tokens). | log |
| F9 | **`symbol` has no module-level constants or dictionary keys** (`_EXTERNAL_ROOTS`, `GUARD_LOG`, `overload_spans`), also with the graph built at HEAD. 57 `ALL_CAPS` and 59 `_private` verdicts sit in the unresolved group. | graph-misses file, `devkb symbol` |
| F10 | **Two guardrail copies run here and the log cannot tell which wrote a row.** `~/.claude/hooks/devkb-guardrail` (0.2.13) and the checkout's script, sharing one log and state files. | file comparison, settings files |

## 2. Opportunities, ranked by size of the effect and cost of the check

| Rank | Change | Size, from the data | Risk | How it is settled without an agent run |
|---|---|---|---|---|
| **1** | **Choose the question by intent** (F2): `locate` and `read-body` ask `symbol` / `symbol --source`; `call-sites` and `in-file` ask `uses` / `pack refactor` as now. | Withheld locate decisions 129 + read-body 127 = **256 of 2,111 (12%)**; the share that resolves to one exact symbol is small (F1: 4%), so the gain rides on item 2 | A definition answer to a "who calls" search misleads: keep the mapping by intent | Replay the logged decisions through the new mapping (`hook_replay.py` reads a run's `stream.jsonl`; the log's `names` and `intent` are enough for a dry run); judge 40 answers by hand against the search, as for the 0.2.13 hook (52 of 120 wrong answers then) |
| **2** | **Answer an ambiguous name with its candidates** (F1): 2 to 8 exact symbols listed as `file:line signature`, capped. | 234 name occurrences are ambiguous exact symbols; 146 have 2 to 8 candidates (100 with 2 to 3). For `locate` and `read-body`: 80 of those. About **+4 points of answered share** on a base of 5.3%, and the answer is short (a candidate is about 100 characters, under 800) | An agent searching the word `build` (21 definitions) wants occurrences, not definitions; list only when candidates are 8 or fewer and intent is `locate` or `read-body` | Same replay and hand judgement; count how often the named file:line contains the search's context |
| **3** | **Answer the names that resolve, say which did not** (F3): partial answer with an explicit "not answered: X, Y" line. | Ceiling **144 decisions (6.8%)**, of which `locate` 42 | A multi-name regex answered for some names reads as complete. The not-answered line is the control, and it exists already for 8 `alongside:partial` answers | Hand judgement of 30 multi-name decisions; the hook's own `verdicts` give the split |
| **4** | **Never cut the Incomplete note; order the pack by value** (F4, F5): Incomplete/Coverage first, then callers, dependents, then tests limited to the direct ones plus a count and the command for the rest. Cap by section, not by cutting the tail. | Removes 15 silent losses of the honesty note; simulated total over the 202 packs 352k to 296k characters (−16%), 90th percentile 4,288 to 2,927; 13 packs still above 800 tokens (3,200 characters) | Fewer tests listed: the test list is what QB1 measured (recall 0.74 to 0.83), so cap by a rank, not an arbitrary 6, and check that recall holds | QB1's scorer on the capped packs: pack-level recall of the tests that matter, no agent needed |
| **5** | **Reclassify word searches as text, not `not-complete`** (F1): a lowercase dictionary word with no exact symbol is a text search. | **0 change for the agent** (it was a pass-through before and after); fixes the denominator: the 47% `not-complete` figure that opened #390 and #391 is overstated by roughly the 52% of names that were never symbols | none | Recompute the table; no run |
| **6** | **Decide the pre-edit Bash policy with a paired measurement** (F6): today it is unmeasured, wired nowhere in this repository, and on 147 of 304 packs it fires on a read. Candidates: (a) as is; (b) write-intent commands only (−61% characters: 641k to 251k); (c) as (a) with item 4's compaction. | up to 160k tokens over four sessions, against a stated cost of one turn being about 41k tokens re-read; the injected file is changed later 74% of the time | The only candidate that changes what an agent reads before it edits; a null result would also be informative | The one experiment worth agent runs in 0.2.16: arms `none`, `hook`, `hook+preedit` on the six hidden-location tickets, 7 runs each, with the replay's pack sizes predicted first |
| **7** | **Index module-level constants and keys as symbols** (F9) so `locate` can answer them. | 57 `ALL_CAPS` + 59 `_private` + dictionary keys inside the unresolved group; today `uses` finds them by text only | Graph schema: node kinds need an ADR (ADR-SDP-DEVKB-001 style rule for devkb's own schema; check devkb's) | Graph-quality benchmark QB: held-out symbol recall before and after |
| **8** | **Rebuild in the background when a search is stale** (F7): the hook starts a detached incremental update (#411) and passes through this once. | `stale-graph` is 468 decisions (22%) overall but 1% after #410, so the value left is small and depends on #411 | Contradicts the guide's "no full rebuild in a hook" only if it blocks; a detached build does not | After #411: stale share on the same tickets before and after |
| **9** | **Tag every log row with the hook's commit** (F10) and remove the user-level copy from this repository's sessions. | Makes every number above attributable | none | A test that each row has a `version` |
| **10** | **Measure the use of `Read` span hints** (29 given, median 51 characters): did the next `Read` use `offset` and `limit`? | 29 hints; effect unknown | none | From the transcripts of runs that logged a hint |

Not recommended: tuning reminders (F8), turning on the router or the tool entry point (0 to 2 queries in 35 runs; router +0.8 turns and +13% cost), a full rebuild inside a hook.

## 3. Intent x outcome (decisions since v0.2.14, all sessions)

| Intent | n | not-complete | stale-graph | duplicate | remind | answered |
|---|---|---|---|---|---|---|
| in-file | 501 | 165 | 187 | 38 | 95 | 14 |
| read-body | 476 | 127 | 143 | 130 | 45 | 9 |
| call-sites | 458 | 156 | 92 | 51 | 105 | 31 |
| locate | 245 | **129** | 30 | 0 | 45 | 40 |
| unknown | 126 | 0 | 0 | 0 | 13 | 41 (hints) |
| list-files | 118 | 0 | 0 | 0 | 56 | 0 |
| call-sites-filtered | 77 | 22 | 14 | 20 | 13 | 6 |
| non-code, count, literal, list-symbols | 113 | 0 | 2 | 0 | 43 | 3 |

`locate` has the highest withheld share (53%) of any intent that the graph is built to answer, and is the intent item 1 and 2 serve.

## 4. What the guide adds, and what it does not

| Guide idea | Verdict against the data |
|---|---|
| 800-token ceiling on every injection | **Adopt for pre-edit** (F4/F5/item 4: 13 of 202 packs exceed it after compaction, 17 before at the 6,000-character cap). The guardrail's answers already comply (maximum 2,260 characters, about 565 tokens) |
| Layer 4: pre-edit pack, direct vs indirect tests | **Adopt the ordering, measure the policy** (items 4 and 6). The guide states the layer is enabled by default; here it is wired nowhere and unmeasured |
| Layer 5: SessionStart index status | **Narrow value**: the plugin already builds in the background; the data's problem is staleness during a session (F7), not at its start. Replace with item 8 |
| Layer 7: miss and refetch telemetry | **Adopt in a better form**: item 9 (version per row) and item 10; the guide's destination file name was wrong (`stream.jsonl` is an input) |
| No default router, no passive pack on `Read`, no rebuild in a hook, no speculative schemas | **Confirmed by this release's data** (router +0.8 turns and +13%; `Read` hints 29, tiny) |
| Layer 6 `UserPromptSubmit` router | Stay off |
| Layer 2 pre-approved `devkb` commands in settings | Check against this repository's `.claude/settings.json` (not present there); a permission list would remove the refusals #369 fixed for benchmarks, for users, too |

## 5. The experiment these items define (no agent run until the replay passes)

1. **Replay, free**: re-run the 2,111 logged decisions through items 1, 2, 3 and 5; report answered share, answer size, and a 40-answer hand judgement of correctness by intent; stop an item whose wrong-answer rate exceeds the 5% floor of SPEC-DKB-007.
2. **QB1 on item 4**, free.
3. **One agent batch**, for item 6 only: `none`, `hook`, `hook+preedit` x 6 tickets x 7 runs (about $20 by the cost of the 0.2.15 batches: $0.15 to $0.44 a run), after the replay has predicted the injected size.
