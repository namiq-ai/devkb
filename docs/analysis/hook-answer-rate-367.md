# How often the guardrail answers a search, replayed (#367)

The guardrail (`scripts/devkb_guardrail.py`) is the part of devkb that reaches an agent without the agent asking. This
note measures how often it answers the searches agents actually make, by replaying archived runs through the
guardrail on `main`, and records, for each kind of search it lets through, whether it should answer it.

## Method

`bench/policy/hook_replay.py` reads a run's `stream.jsonl` and sends every Grep, Bash and Read call (the hook's
matcher) to the guardrail as the PreToolUse event Claude Code would have sent: same order, same session id, a HOME of
its own per stream, the run's checkout path (also written `~/...`) rewritten to the replay's checkout, and the working
directory a `cd` left for the next calls. A call the guardrail logs a line for is a *decision*; the others are skipped,
as the hook skips them. The hook runs with the live limit (20 s); none came near it (2.5 s at most).

- An **answer** is a decision whose text reached the agent: the guardrail marks the decision's log line with what it
  gave (`emit()`). A decision whose answer was built and then lost has no mark, even when the session's reminder was
  printed in its place; it is counted as *built, not delivered*. A span hint on a read is an answer too.
- A **code-name search** is one whose intent is `call-sites`, `call-sites-filtered`, `locate`, `read-body` or
  `in-file`.
- Each row says whether the run had already changed a file (`after_edit`). The replay searches the run's base as it
  was, so after the first edit it sees the base's code where the live hook saw the agent's; live, some of those
  searches would have been passed through as `stale-graph`.
- Where the stream recorded the hook's own output (`--include-hook-events`), each row carries it (`live_chars`), so
  the replay can be checked against what the agent was really given.

The checkout for each run is its base commit exported as the harness exports it (`git archive`, a fresh `git init`,
`bench/policy/accept/` removed), with the graph built by main's code and the C/C++ corpus copied in and built where the
runs searched it.

**Check against the live runs.** For the 6 recent runs whose live hook was main's (#382, #383 and #367, base 2e216fc:
the guardrail has not changed since), replay and live agree on 19 of 19 decisions, 3 of them answers. For the 27 runs
of #337's experiment, whose live hook was their base's older guardrail, they agree on 148 of 166.

## Baseline on main (guardrail at 2acb3da)

| Streams | Runs with a decision | Decisions | Answered | Code-name searches answered | before the first edit | Built, not delivered | Characters per answer (median, max) |
|---|---|---|---|---|---|---|---|
| 0.2.14 baseline, devkb arm | 19 of 24 | 36 | 2 (6%) | 2 of 30 | 2 of 29 | 2 | 451, 627 |
| 0.2.14 re-run | 6 of 8 | 15 | 2 (13%) | 2 of 13 | 2 of 12 | 1 | 275, 275 |
| this session (#337 experiment, #382, #383, #367) | 33 of 36 | 185 | 18 (10%) | 12 of 160 (8%) | 7 of 87 | 5 | 250, 348 |

The 18 recent answers include 5 span hints on reads; 13 answered searches.

**Main answers fewer of the 0.2.14 searches than the 0.2.14 hook did.** On the re-run streams the 0.2.14 hook
delivered 3 answers (recorded in the streams); main delivers 2 of the same 15 calls: one new (`run_suite`, a
substitute), and two lost: one by design (#281: the search's own `| head -20` would cut the answer short), one to a
crash, #393: a search piped into a bare `head` or `tail` makes `output_limit()` raise after the answer is built and
logged, so the agent gets nothing, or only the reminder. The same crash drops 2 answers on the baseline streams and 5
on the recent ones.

The 0.2.14 hook log's "57 decisions" are log lines: 36 decision lines and 21 reminder lines; 9 of the reminders were
calls with no decision line, so the log covers 45 calls. The replay finds 36 because main no longer reminds on literal
searches (#329).

## What the recent code-name searches got, and what to do about each group

| Group | n | of them after the first edit | Example | Decision |
|---|---|---|---|---|
| Answered | 12 | 5 | `alongside` for `HOOKS` in a pipe; `_import_descriptors` in a compound command | |
| Built, not delivered (#393) | 5 | | `grep -rn "devkb_nav\|devkb_selftest" ... \| head` | **fix the crash** (#393): these are answers already. |
| `duplicate:*`: every name complete, grep prints these same lines | 38 | | `grep -n "def run_suite" -A25 policybench.py` | **leave to grep.** The answer would repeat grep's own lines (#217); a teach line in their place changed nothing (#375), so it stays off. |
| Every name `cannot-resolve` (several symbols share it), or `cannot-resolve` with `no-match`/`incomplete` | 39 | 19 | `transcript`, `_msg`, `checkout`, `environ` | **resolve within the searched files** (#390): 22 are `read-body`/`in-file` searches limited to files, where the name is usually defined once; the 17 call-site and locate searches are repository-wide and this does not reach them. |
| Several names, one or more `complete`, held back by another | 31 | 9 | `template_for` + `PREREGISTER_POST` | **answer the complete names beside grep** (#391); grep still runs and prints the rest. |
| Only `no-match` names | 26 | 16 | `price\|per_mtok\|usd`, `RuntimeError`, `POLICY_`; and names the agent had just written | **leave to grep**: plain words, builtins and prefixes have no symbol; a name written after the base is not in the base's graph (live, the hook would see a stale graph). |
| Only `incomplete` | 6 | | | **leave**: the graph says it cannot follow every call; grep runs. |
| The search's own cut (`cut:20`) | 3 | | `... \| head -20` | as today (#281). |

**Upper bound.** If #393 were fixed and #390 and #391 answered every search in their groups, 87 of the 160 code-name
searches (54%) would get an answer. That overstates it: 33 of those 87 come after the run's first edit, where the live
hook may see a stale graph, and 17 are repository-wide `cannot-resolve` searches that #390 does not reach.

**What the agent did next.** The replay keeps each run's next call, so it cannot show whether an answer would change
it; only a live run can. After the 13 answered searches the next calls were a read of the same code in 7 (`Read`, `sed -n`), an edit in 2, another
grep in 2, a new test file and a test run; none was a devkb query. In the live #382, #383 and #367 runs (9 devkb-arm runs) the hook gave two graph answers (both in
#382, 289 and 348 characters) and one span hint; the agents queried devkb only to run the ticket's reproduction.

## Target

#367 proposed "at least half of the code-name searches get an answer or a replacement". On these runs that is about
the upper bound above (54%), which the edits and repository-wide names make out of reach.
**Proposed instead (owner to confirm):** at least 30% of the recent code-name searches answered on this replay (from
8%), with no answer the source contradicts, and the median answer under `MAX_ANSWER`; measured again after #393, #390
and #391, in that order (#393 alone gives 17 of 160, 11%).

## Data

- Replay output, one JSON file per ticket (`base-*`, `rerun-*`, `recent-*`), the streams and the scripts that made
  them: `devkb-benchmark-367-hook-replay-archive.tar.gz`, beside the checkout.
- Inputs: `devkb-benchmark-0.2.14-archive.tar.gz`, `devkb-benchmark-0.2.14-rerun-archive.tar.gz`,
  `devkb-benchmark-337-hide-start-archive.tar.gz`, and the #382/#383/#367 runs.
