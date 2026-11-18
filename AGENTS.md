<!-- devkb:begin (managed by `devkb init`; edit outside this block) -->
## devkb: ask the graph before you read or change code

This repository has a graph of its code in `.devkb/`: calls, tests, raised errors, commits, configuration. One call
returns what would take a dozen searches and file reads, and every item carries the line of code that proves it. The
graph does not hold *how the code is written*: to copy a pattern or learn a style, read the file.

**Choose by what you are about to do:**

**Instead of grep, to read code**: the graph holds every definition with its exact lines, so ask it rather than guess
`grep -A25`:
- `symbol(query)` (shell: `devkb symbol QUERY --source`): where a name is defined, with exact lines and the signature;
  `source=True` prints the body. A query can be a name, `Class.method`, `path::name`, a glob `parse_*`, `re:regex`, a
  prefix or a few words; a typo is tolerated, and below the confidence floor it says there is no match and suggests names.
- `outline(path)` (shell: `devkb outline PATH`): a file's symbols in order with line ranges, and its imports: look before you read.
- `uses(name)` (shell: `devkb uses NAME`): where a name, constant, module or key appears, grouped by the symbol that
  contains each use. Text matches, not resolved references.
- `search_docs(query)` (shell: `devkb docs QUERY`): what the documentation says, with the heading of each hit.
A symbol in a language that stores no end line (TypeScript, JavaScript) is reported as "end unknown": read from its start.


| You are about to... | Use | You get |
|---|---|---|
| open a file to see what depends on it, or edit it | `pack(kind="file", subject=PATH)` (shell: `devkb pack --project . file PATH`) | the functions other files call, the files that depend on it, the tests to run |
| change a function's behaviour or signature | `pack(kind="change", subject=NAME, path=PATH)` (shell: `devkb pack --project . refactor NAME`) | callers at any depth, tests among them |
| start from an error message or a failing request | `pack(kind="error", subject="MESSAGE")` | what raises it, the handlers that reach it |
| find who calls one function directly | search with grep | one hop: a pack adds a step and saves nothing |
| learn how a pattern is written, to copy it | read the file | the graph does not store this |
| decide which tests to run | `tests_to_run` or `tests_for` | the tests, ranked |
| review a commit or a diff | `review_pack` | changed functions, outside callers, untested changes |
| find a setting or a service | `config` | where it is declared and read |

**How to work:**
1. Ask first, read second. Run the pack for a file before you read it to judge impact and before your first edit of it.
   In Claude Code the devkb hook also adds that pack to your first Edit or Write of each file; read it, then continue.
2. A pack marked **Complete** is the whole answer: do not search again to check it. If it is Incomplete, search only the
   files it names. If it says files changed since the graph was built, re-read those files.
3. After editing, run the tests the pack named first, then the full suite. If you edited many files, rebuild first:
   `devkb build --project .` (a few seconds on most repositories).
<!-- devkb:end -->

## Developing devkb: devkb first, logged (#126)

This repository is devkb itself, so every session that works on it is also a test of it.

1. **Ask devkb before searching by text.** For "where is X defined", "who calls / uses X", "what is in this file",
   "what does changing X touch" and "which tests cover X", use devkb from the shell: the released `devkb` on your
   PATH, `devkb symbol|outline|uses|docs|pack ... --project .` (the shell forms of the tools above). This repository
   has no MCP server on purpose: its 12 tool definitions cost about 3k tokens on every model call, and agents chose
   the shell anyway (`docs/analysis/devkb-none-mcp-cli.md`). The same applies to
   the C/C++ corpus (`~/.cache/devkb/cpp-corpus/<repo>`, `--project` that path). Rebuild with
   `devkb build --project .` when the graph is older than the code you are reading.
2. **Check the answer against the source** before relying on it. grep, sed and Read remain right for filtering
   command output, literal strings, confirming an edit, and questions devkb has no tool for.
3. **You do not keep the query log: devkb does.** Every query it answers, from the MCP server or the command line,
   is recorded in `.devkb/process-api-telemetry.jsonl` with what was asked (#127). In your final report, name any
   devkb answer that turned out wrong, misleading or silently incomplete, with the query and what the source showed.
4. **A wrong, misleading or silently incomplete answer is a defect.** File one issue per defect (reproduce
   command, actual, expected, where to start, done when) before anyone fixes it.
5. **The guardrail answers from the graph or gets out of the way (#131).** `.claude/settings.json` runs
   `scripts/devkb_guardrail.py` before Grep and grep / rg / git grep searches. When every name a search asks about
   resolves in the graph with coverage Complete, devkb's answer is the search's result, in the same call (beside the
   output when the command does more than search; repeat the identical search for grep's raw lines). Otherwise the
   search runs untouched, exactly as without devkb. It never refuses. `DEVKB_GUARDRAIL=0` turns it off for a
   benchmark's control arm.

Why: SPEC-DKB-004 was first written with grep; redone through devkb, the same questions found three devkb defects
(#114–#116). Use on real work is how devkb's gaps are found. Measured on three fixes (#126): agents asked to keep a
log wrote none in 6 of 6 runs, and a reminder at every search (about 12 per run) was ignored, so devkb now logs
itself and the reminder comes once.

6. **Review the graph misses at the end of a task (#133).** When a search passes through to grep because devkb
   could not answer (cannot-resolve, no-match, incomplete, stale) and grep found code, the guardrail's PostToolUse
   hook (`scripts/devkb_guardrail_post.py`) appends one line to `.devkb/graph-misses.jsonl` (local only;
   `DEVKB_MISSLOG=0` turns it off). Run `devkb misses --project .`, check each ticket draft against the source, and
   file the ones that are real. Nothing is filed automatically.

7. **Every completed ticket carries its execution result (#139).** When a ticket's PR merges, add a comment headed
   **Execution result** to the ticket, before reporting the work as finished:
   - where it was done: the PR number and the merge commit;
   - what it does now, in user terms, with one concrete example;
   - the dual-mode table (no devkb against devkb CLI: runs, model calls, cost, and the acceptance columns), with one
     line on what it shows;
   - problems found and fixed on the way, including mistakes in the measurement itself;
   - the follow-ups filed (issue numbers) and where the raw data is.

   Example: #133.

8. **After a ticket, check the graph misses and follow them up (#141).** Right after its execution result (rule 7):
   - **Check:** run `devkb misses --project .` here and in every corpus repository the work searched
     (`~/.cache/devkb/cpp-corpus/<repo>`). A search devkb could not answer that the log missed is a finding too.
   - **Summarize:** add a **Graph misses** section to the execution-result comment: count by verdict and name, one line
     on what each group means; "none" if there were none.
   - **Follow up:** file one ticket per real group (checked against the source), from its `devkb misses` draft. Its first
     line reads **Follow-up of #N** (the original ticket), and the original's comment lists the new numbers. Noise (a
     stale graph, a match only in tests or docs) is noted in the summary, not filed.
   - **Clear:** move the reviewed lines from `.devkb/graph-misses.jsonl` to `.devkb/graph-misses-reviewed.jsonl` with
     their ticket numbers, so the next check starts clean.
