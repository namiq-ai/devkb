# Quality benchmarks for the questions grep cannot answer

Status: design, nothing built. The turn and cost benchmarks cannot see what the reference architecture is for: which tests a
change endangers, which earlier issue a new one repeats, whether a release breaks users, what an epic will touch. These four
measure quality, from ground truth built mechanically from this repository's history, offline, with no model runs. Counts
below were checked on 2026-11-21.

## Common rules

- **Ground truth from history, not from labelling.** Each item has an answer that happened (a test that guards a change, a
  linked issue, a removed command, the files a ticket's commits touched).
- **No leakage.** The graph is built at the commit before the item; a candidate pool contains only what existed then; the line
  that states the answer (a "Follow-up of #N" line, a changelog entry) is removed from the query.
- **A baseline that grep or git can reach**, built before devkb is touched, because headroom decides whether schema work is
  worth starting. **If the baseline already reaches 0.9 of the achievable score, the item is closed without building anything.**
- **Report** the number of items, a 90% bootstrap interval over items, every arm, and every item the method failed on.
- **Decision rule for each:** build when the graph arm is above the baseline by the stated margin on the interval's lower bound;
  otherwise iterate once, then park.

## QB1. Tests to run and blast radius (change to PR)

Question: for a change, does `pack file`, `tests_to_run` or `review_pack` name the tests that exercise it?

- **Items.** 105 of the last 280 commits change `devkb/*.py` and `tests/*.py` together.
- **Truth (dynamic coverage).** One `pytest --cov --cov-context=test` run at a snapshot commit records which test covers which
  function. For each later commit that changes a function present at the snapshot, the truth is the set of tests whose context
  covers that function. About 6 snapshots, 10-15 following commits each; function level because lines move.
- **Query.** At the snapshot, for each changed source file: `devkb pack file F` (its "tests to run"), `tests_for`, and `review_pack` on the diff.
- **Baselines.** (1) tests whose text imports the module; (2) the name convention `test_<module>`; (3) `grep -l` of each changed function's name in `tests/`.
- **Metrics.** Recall of the covering tests (primary), precision, tests listed (tokens), and the **missed-guard rate**: changes
  where a covering test existed and none was named.
- **Why first.** The suspected defect (`tests_for` under-lists and says "no test calls it" for functions reached through their
  callers) is measurable here and nowhere else; the truth is cheap (one coverage run per snapshot, about 10 minutes); and it is
  the quality claim behind "decide which tests to run".
- **Gate.** Recall above the best baseline by 15 points, at most 40 tests listed per change.

## QB2. Related-issue and owner retrieval (triage)

Question: given a new issue, does the graph find the issue it repeats or follows, and the code that owns it?

- **Items.** 222 issues, 162 closed. 73 carry "Follow-up of #N", 3 are explicit duplicates (label or "duplicate of"). Too few
  true duplicates to score alone, so the task is *related-issue retrieval* with the link as truth, and the 3 duplicates reported
  separately. 76 items.
- **Truth.** The linked parent issue; for owners, the files the parent's fix commits changed (commits that cite `(#N)`: 151).
- **Query.** The new issue's title and body with the link line removed; candidates are issues numbered below it.
- **Arms.** (1) TF-IDF over title and body (the baseline a script could build); (2) `devkb docs` over the same text;
  (3) structural: the code names in the issue, resolved in the graph, to the tickets whose commits touched those files;
  (4) the two combined.
- **Metrics.** Recall at 1, 5 and 10, MRR; owner-file hit at 5.
- **Gate.** The combined arm above the baseline by 10 points of recall at 5. If the structural arm alone cannot reach the issues
  the baseline misses, the graph adds nothing to triage and `ErrorSignature` is not built.

## QB3. Release audit (PR to release)

Question: does the audit flag the changes that break a user, and stay quiet about the rest?

- **Items.** 17 tags, 16 consecutive intervals. Release notes are generated PR lists with no breaking flag and there is no
  changelog, so the truth is mechanical.
- **Truth (a differential oracle independent of the graph).** For each tag, from `git archive`: every CLI subcommand and flag
  (`--help`, recursively), every MCP tool name and input schema, the graph's node types and edge verbs, the documented config
  keys. Removed, renamed or newly required items are *breaking*; added items *additive*; the rest *internal*.
- **Query.** The audit for tag A to B: the public entities the diff touches and a verdict.
- **Baselines.** (1) commit subjects (`feat`, `fix`, `!`, "remove"); (2) the file list alone.
- **Metrics.** Breaking-change recall (a removal missed is a **false calm**, counted on its own), precision, verdict accuracy.
- **Gate.** Recall of 0.95 or more with precision of 0.8 or more. Pre-1.0 tags may break anything, so the verdict is
  breaking / additive / internal, not a SemVer number.

## QB4. Epic to features (impact of a specification)

Question: from an epic's text, does the graph predict the code its features will touch, before they are written?

- **Items.** Specs with their tickets: SPEC-DKB-004 (16), 007 (12), 005 (10), 006 (10), 008 (2); plus 13 epic-like issues.
  A leave-one-ticket-out variant gives about 50 items: predict one ticket's files from the spec section and the ticket's title.
- **Truth.** The files changed by the commits that cite the ticket.
- **Query.** The spec or epic text with the ticket list removed.
- **Arms.** (1) TF-IDF over file paths and symbol names; (2) grep of the terms the text names; (3) graph: the named symbols,
  their callers and dependents, and the documents that mention them.
- **Metrics.** File recall at 10 and 20, precision, and whether the predicted files split into groups that match the actual
  tickets (a vertical slice).
- **Gate.** Recall at 20 above the best baseline by 10 points. A graph edge such as GOVERNS is built only if the existing
  mention edges cannot reach the files the baseline misses.

## Order and cost

| order | benchmark | first deliverable | effort |
|---|---|---|---|
| 1 | QB1 | the truth builder (coverage snapshots) and the three baselines' recall, before any change | about 1 day |
| 2 | QB2 | the pair extractor, the TF-IDF baseline, the structural arm | about 1 day |
| 3 | QB3 | the surface extractor for 17 tags and the diff oracle | about 1.5 days |
| 4 | QB4 | the ticket-to-files table and the baselines | about 1 day |

Each first deliverable is a baseline number. The loop then decides: baseline near the ceiling, close the item; headroom,
change devkb behind a flag, re-run the same benchmark, ship only above the gate.
