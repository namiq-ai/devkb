# How often the guardrail answers a search, replayed (#367)

The guardrail (`scripts/devkb_guardrail.py`) is the part of devkb that reaches an agent without the agent asking. This
note measures how often it answers the searches agents actually make, by replaying archived runs through the
guardrail on `main`, and records, for each kind of search it lets through, whether it should answer it.

## Method

`bench/policy/hook_replay.py` reads a run's `stream.jsonl` and sends every Grep call and every Bash call to the
guardrail as the PreToolUse event Claude Code would have sent: same order, same session id, the run's checkout path
rewritten to the replay's checkout. A call the guardrail decides on (it writes a line to its log) is a *decision*;
other calls (`ls`, a test run) are skipped, as the hook skips them. Each decision is printed with its action, reason,
intent, names and verdicts, the characters the agent would have been given, and the agent's next call in the run.

```
python bench/policy/hook_replay.py --repo CHECKOUT RUN_DIR ...      # one JSON line per decision, then a summary
```

The checkout for each run is its base commit exported as the harness exports it (`git archive`, a fresh `git init`,
`bench/policy/accept/` removed), with the graph built by main's code, and the C/C++ corpus copied in and built where
the runs searched it. An *answer* is a decision that gave the agent text: `substitute`, `read-answer`, `alongside` or
`teach`. A *code-name search* is one whose intent is `call-sites`, `call-sites-filtered`, `locate`, `read-body` or
`in-file`.

The replay counts one decision per call. The hook log counts lines, and the first search of a session logs two (its
decision, then the session's one reminder), so the 0.2.14 figure of "57 decisions" is 36 calls.

## Baseline on main (guardrail at 2acb3da)

| Streams | Runs with a decision | Decisions | Answered | Code-name searches | of them answered | Characters per answer (median, max) |
|---|---|---|---|---|---|---|
| 0.2.14 baseline (#301-#331, devkb arm) | 19 of 24 | 36 | 3 (8%) | 30 | 3 (10%) | 595, 627 |
| 0.2.14 re-run (final harness) | 6 of 8 | 15 | 3 (20%) | 13 | 3 (23%) | 513, 595 |
| this session (#337 experiment, #382, #383, #367) | 33 of 36 | 180 | 14 (8%) | 161 | 13 (8%) | 266, 595 |

The guardrail changes merged since 0.2.14 (#274, #280, #281, #359) did not move the rate: replaying the 0.2.14
baseline through main gives 3 answers, as the live runs had 4. #367 inferred that 8 of the 20 `not-complete`
pass-throughs would now be answered; the replay finds 19 still `not-complete`.

What the 161 recent code-name searches got:

| Group | n | Example | Decision |
|---|---|---|---|
| Answered | 13 | `alongside` for `HOOKS` in a pipe; `substitute` for `KEEP_PROPS` | |
| `duplicate:*`: every name complete, and grep prints these same lines | 42 | `grep -n "def run_suite" -A25 policybench.py` | **leave to grep.** The answer would repeat grep's own lines (#217); the teach line in their place did not change behaviour (#375: 0 queries after 17 teach lines), so it stays off. |
| One name, `cannot-resolve` (several symbols share it) | 30 | `transcript`, `_msg`, `checkout`, `environ` | **answer when the search names its files**: in a `read-body` or `in-file` search the name is usually defined once in the files searched. Resolve it within them; answer only when exactly one definition is there. Follow-up. |
| Several names, one or more `complete`, held back by another | 33 | `template_for` + `PREREGISTER_POST`; `_resolve` + `_by_name` | **answer the complete names beside grep**: grep still runs and prints the rest. Today only `call-sites`/`locate` searches with nothing else unusual get this (`ambiguous:*`, #274). Follow-up. |
| Several names, `cannot-resolve` with `no-match` or `incomplete`, none complete | 9 | `run_one` + `policybench` | as the one-name `cannot-resolve` group: resolve within the searched files, then answer what resolves beside grep. |
| Only `no-match` names | 21 | `price\|per_mtok\|usd`, `RuntimeError`, `os.environ`, `POLICY_` | **leave to grep**: plain words, builtins and prefixes have no symbol; grep is the right tool and `uses` would print the same text matches. |
| `incomplete` | 6 | | **leave**: the graph says it cannot follow every call; grep runs. |
| Other (string keys, answers cut at the cap, one body) | 7 | | as today. |

The 0.2.14 baseline's 30 code-name searches split the same way: answered 3, duplicate 5, one name `cannot-resolve` 8,
several names with one complete 4, `cannot-resolve` with others 2, only `no-match` 5, other 3.

If the follow-ups answered every search in their groups, 85 of 161 code-name searches (53%) would get an answer, so the
upper bound is just above the ticket's proposed half. The other 76 are grep's job by design (duplicates, plain words,
incomplete names) or are already handled.

**What the agent did next.** After each of the 14 answers in the recent replay, the agent's next call in the run was a
read or an edit of the same file (`sed -n`, `Read`, `python3 - <<E`). The replay keeps the run's next call, so it
cannot show whether an answer would change it; only a live run can. In the live #382, #383 and #367 runs (9 devkb-arm
runs), the hook gave 0-3 outputs per run, all of them the reminder; no run queried devkb.

## Target

#367 proposed "at least half of the code-name searches get an answer or a replacement". On these runs that is the
upper bound (53%), reached only if every search in the two answerable groups resolved to one definition.
**Proposed instead (owner to confirm):** at least 35% of code-name searches answered on the replay of the recent
streams (from 8%), with no answer the source contradicts, and the median answer under `MAX_ANSWER`. The two
follow-ups are the way there; each is measured with this replay before and after.

## Data

- Replay output: one JSON file per ticket, `base-*.jsonl`, `rerun-*.jsonl`, `recent-*.jsonl`, archived with the
  #367 runs (`devkb-benchmark-367-hook-replay-archive.tar.gz`, beside the checkout).
- Inputs: `devkb-benchmark-0.2.14-archive.tar.gz`, `devkb-benchmark-0.2.14-rerun-archive.tar.gz`,
  `devkb-benchmark-337-hide-start-archive.tar.gz`, and the #382/#383/#367 runs.
