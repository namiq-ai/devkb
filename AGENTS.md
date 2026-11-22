<!-- devkb:begin (managed by `devkb init`; edit outside this block) -->
## devkb: ask the graph before you read or change code

This repository has a graph of its code in `.devkb/`: calls, tests, raised errors, commits, configuration. One call
returns what would take a dozen searches and file reads, and every item carries the line of code that proves it. The
graph does not hold *how the code is written*: to copy a pattern or learn a style, read the file.

**Choose by what you are about to do.** Every row gives the shell command; where the devkb MCP server is configured
(`.mcp.json`), the tool named in brackets does the same.

**Instead of grep, to read code**: the graph holds every definition with its exact lines, so ask it rather than guess
`grep -A25`:
- `devkb symbol QUERY --source` (MCP: `symbol`): where a name is defined, with exact lines and the signature, and its
  body. A query can be a name, `Class.method`, `Class::method`, `path::name`, a glob `parse_*`, `re:regex`, a prefix
  or a few words; a typo is tolerated, and below the confidence floor it says there is no match and suggests names.
- `devkb outline PATH` (MCP: `outline`): a file's symbols in order with line ranges, and its imports: look before you read.
- `devkb uses NAME` (MCP: `uses`): where a name, constant, module or key appears, grouped by the symbol that
  contains each use. Text matches, not resolved references.
- `devkb docs QUERY` (MCP: `search_docs`): what the documentation says, with the heading of each hit.
A symbol in a language that stores no end line (TypeScript, JavaScript) is reported as "end unknown": read from its start.

| You are about to... | Run | You get |
|---|---|---|
| open a file to see what depends on it, or edit it | `devkb pack --project . file PATH` (MCP: `pack(kind="file", subject=PATH)`) | the functions other files call, the files that depend on it, the tests to run |
| change a function's behaviour or signature | `devkb pack --project . refactor NAME` (MCP: `pack(kind="change", subject=NAME, path=PATH)`); `NAME` may be `Class::method` | callers at any depth, tests among them |
| start from an error message or a failing request | `devkb pack --project . error "MESSAGE"` (MCP: `pack(kind="error", subject="MESSAGE")`) | what raises it, the handlers that reach it |
| find who calls a function | `devkb uses NAME` (with the devkb guardrail installed, a grep for it is answered from the graph when the answer is Complete) | the callers, grouped by function, with the line of each |
| learn how a pattern is written, to copy it | read the file | the graph does not store this |
| decide which tests to run | `devkb pack --project . file PATH`: its "tests to run" (MCP: `tests_to_run`, `tests_for`) | the tests, ranked |
| review a diff | `devkb pack --project . file PATH` for each changed file (MCP: `review_pack`) | outside callers and the tests that reach the change |
| find a setting or a service | `devkb uses KEY` (MCP: `config`) | where the key is declared and read |
| see where the graph could not answer | `devkb misses --project .` | searches that fell through to grep and found code, as ticket drafts to check and file |

`pack` accepts `Class::method`. When the graph has no answer for a name it does not stop: it gives the text matches
for it, grouped by function as `uses` does, and says so.

**How to work:**
1. Ask first, read second. Run the pack for a file before you read it to judge impact and before your first edit of it.
   Nothing does this for you unless you installed a hook with `devkb init --claude-hook`.
2. A pack marked **Complete** is the whole answer: do not search again to check it. If it is Incomplete, search only the
   files it names. If it says files changed since the graph was built, re-read those files.
3. After editing, run the tests the pack named first, then the full suite. If you edited many files, rebuild first:
   `devkb build --project .` (a few seconds on most repositories).
<!-- devkb:end -->

## Developing devkb: devkb first, logged (#126)

This repository is devkb itself, so every session that works on it is also a test of it. Follow these in order.

**Per-ticket checklist: read it before you start a ticket, and again before you call it done.** Every ticket gets all five;
skipping one is a defect in the work, not a shortcut (the 0.2.14 harness fixes #301-#304 skipped 2-5 and had to be
backfilled).
1. **Hidden check.** `bench/policy/accept/<N>.py`, written from the ticket's *Expected* list as a black box (it takes the
   checkout path, prints one JSON line with `pass`). Run it on the ticket's base commit (must fail) and on the fix (must pass).
2. **Two arms, from the base commit, before you look at your own fix.** `none` (no devkb) and `main` (devkb CLI), same model,
   same prompt, one shuffled batch, at least 3 repetitions (what 3 runs can and cannot claim is in `docs/BENCHMARK.md`, "How many runs a claim needs"):
   `POLICY_ARMS=none,main POLICY_MAIN=<base sha> .venv/bin/python bench/policy/policybench.py run <N> --reps 3`, then `score <N>`.
   Every arm runs the same suite (#331): the harness removes the guardrail's tests from all arms, and the table prints each arm's
   collected-test count and first-call context, with a warning when the counts differ. For a ticket about the guardrail itself,
   set `POLICY_EQUAL_SUITE=0` and use `nonekeep` as the control.
   The rules are `docs/BENCHMARK.md`'s: same model in every arm, one session per batch, pinned commits, never tune on the
   benchmark's own tasks, report everything (arms that cost more, runs that failed, runs cut off).
3. **PR review, two ways.** With and without devkb's `review_pack` (#316), posted as a GitHub review (`gh pr review`), then
   `bench/review/gate.py PR FINDINGS.json`. Merge only as the owner on the owner's host, and only when the gate says `merge`;
   a PR from anyone else is reviewed and never merged.
4. **Execution result comment** on the ticket (rule 7 below): where it was done, what it does now, the dual-mode table from
   step 2, problems found, follow-ups.
5. **Graph misses**: `devkb misses --project .`, summarised in that comment (rule 7).

1. **Run the devkb of this checkout.** Use `.venv/bin/devkb`, not the `devkb` on your PATH: the released 0.2.11 lacks
   `devkb misses` (#133), `Class::method` in `pack` (#132) and the query log (#127), so rule 7 would fail with it. Once
   the next release ships these, the one on your PATH is fine. Examples below write `devkb` for either.
2. **Ask devkb before searching by text.** For "where is X defined", "who calls / uses X", "what is in this file",
   "what does changing X touch" and "which tests cover X", use `devkb symbol|outline|uses|docs|pack ... --project .`
   from the shell. This repository has no MCP server on purpose: its 12 tool definitions cost about 3k tokens on every
   model call, and agents chose the shell anyway (`docs/analysis/devkb-none-mcp-cli.md`). The same applies to the C/C++
   corpus (`~/.cache/devkb/cpp-corpus/<repo>`, `--project` that path). Rebuild with `devkb build --project .` when the
   graph is older than the code you are reading.
3. **Check the answer against the source** before relying on it. grep, sed and Read remain right for filtering
   command output, literal strings, confirming an edit, and questions devkb has no tool for.
4. **You do not keep the query log: devkb does.** Every query it answers is recorded in
   `.devkb/process-api-telemetry.jsonl` with what was asked (#127). In your final report, name any devkb answer that
   turned out wrong, misleading or silently incomplete, with the query and what the source showed. (Measured on three
   fixes, #126: agents asked to keep a log wrote none in 6 of 6 runs, and a reminder at every search was ignored.)
5. **A wrong, misleading or silently incomplete answer is a defect.** File one issue per defect (reproduce command,
   actual, expected, where to start, done when) before anyone fixes it.
6. **The guardrail answers from the graph or gets out of the way (#131).** `.claude/settings.json` runs
   `scripts/devkb_guardrail.py` before Grep and grep / rg / git grep searches. When every name a search asks about
   resolves in the graph with coverage Complete, devkb's answer is the search's result, in the same call (beside the
   output when the command does more than search; repeat the identical search for grep's raw lines). Otherwise the
   search runs untouched, exactly as without devkb. It never refuses. Each answer ends with the devkb command that
   gives it, so the next such question can go to devkb directly (#267; `DEVKB_GUARDRAIL_TEACH=0` turns that line
   off). `DEVKB_GUARDRAIL=0` turns the guardrail off for a benchmark's control arm.
7. **Every completed ticket carries its execution result (#139), then its graph misses (#133, #141).** When a ticket's
   PR merges, add a comment headed **Execution result** before reporting the work as finished:
   - where it was done: the PR number and the merge commit;
   - what it does now, in user terms, with one concrete example;
   - the dual-mode table (no devkb against devkb CLI), with one line on what it shows. Columns: Turns, Model calls,
     Grep, Read, devkb nav / own-code, Substituted, Tokens, Cost, Suite, acceptance;
   - problems found and fixed on the way, including mistakes in the measurement itself;
   - the follow-ups filed (issue numbers) and where the raw data is.

   Then review the graph misses. When a search passes through to grep because devkb could not answer (cannot-resolve,
   no-match, incomplete) and grep found code, the guardrail's PostToolUse hook (`scripts/devkb_guardrail_post.py`)
   appends a line to `.devkb/graph-misses.jsonl` (local only; `DEVKB_MISSLOG=0` turns it off). A stale graph is a
   note on a line, not a verdict. Then:
   - **Check:** run `devkb misses --project .` here and in every corpus repository the work searched
     (`~/.cache/devkb/cpp-corpus/<repo>`), and check each ticket draft against the source. A search devkb could not
     answer that the log missed is a finding too.
   - **Summarize:** add a **Graph misses** section to the execution-result comment: count by verdict and name, one line
     on what each group means; "none" if there were none.
   - **Follow up:** file one ticket per real group, from its `devkb misses` draft. Its first line reads
     **Follow-up of #N** (the original ticket), and the original's comment lists the new numbers. Noise (a stale
     graph, a match only in tests or docs) is noted in the summary, not filed. Nothing is filed automatically.
   - **Clear:** move the reviewed lines from `.devkb/graph-misses.jsonl` to `.devkb/graph-misses-reviewed.jsonl` with
     their ticket numbers, so the next check starts clean.

   Example: #133.
