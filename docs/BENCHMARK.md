# The devkb benchmark: adding a repository

The benchmark asks one question per repository: with the same model in every arm, does giving an agent devkb's graph
make a developer task cheaper at equal quality? Every repository is listed in [`bench/repos.yaml`](../bench/repos.yaml)
and goes through the same pipeline.

## Add a repository

1. Add an entry to `bench/repos.yaml`: a public https URL, a full commit hash, `kind` (`web` if it serves HTTP routes
   with FastAPI- or Flask-style decorators, `cli` for a command-line tool or a library), a size, a seed and the licence.
   The task generators read Python source, so the repository must be mostly Python.
2. Try it locally (free, a few seconds to a few minutes):

   ```bash
   make dev
   .venv/bin/python -m devkb.bench.pipeline prepare <id>
   ```

   It prints how many tasks the generator found and how good the packs are (below). A repository where the generator
   finds no task, or where the packs score low, is still worth a pull request: say so in it.
3. Open a pull request. The `bench` workflow runs the same free stage for every entry and writes each repository's
   pack accuracy into the job summary.

## What the free stage does

| Step | Output (in `bench-work/<id>/`) |
|---|---|
| Clone at the pinned commit | `checkout/`: the tree the agents will search, with no graph inside it |
| Build the graph | `graph/`: the snapshot the tools and packs read, at the same commit |
| Generate tasks, truth from source | `tasks.json`: `web` change-impact, error-to-handler and refactor tasks (`confirm_tasks.py`); `cli` error traces and refactor tasks (`cli_tasks.py`). Truth comes from import-resolved calls, never from the graph |
| Build packs | `tasks.packs.json`: each pack built only from what the task prompt states |
| Check the packs | `pack-check.json`: each pack read as an answer and scored against the truth |

The pack check is the cheapest test of the graph on a new repository. A score below 1.0 is a graph gap; a pack that
says **Complete** and still scores below 1.0 is the worst kind, because an agent stops searching. Both are listed.

The pack check cannot see a mistake the pack and the truth share. On lnbits, both missed every caller that imported
`get_wallet` through its package's `__init__.py` (22 of 39 files), so the pack scored 1.0 while the agents who found
those callers were marked down. `prepare` therefore also runs `bench/truth_check.py`, a second implementation of the
refactor truth that shares no code with the graph or the generators, and fails when it proves a caller the truth lacks
(`pack-check.json`, `truth_check`).

## Run the agents (costs money)

Locally, with the Claude Code CLI installed and signed in:

```bash
.venv/bin/python -m devkb.bench.pipeline run <id> --arms plain,core,lean,pack --reps 5 --model sonnet
.venv/bin/python -m devkb.bench.pipeline report <id> --model sonnet
```

`report` ends with the per-task detail (median cost, mean score and median turns per arm; each score part per task
kind; the graph tools each arm called), also available for any runs file as `pipeline detail --runs FILE ...`.

On GitHub: Actions → bench → Run workflow, tick `run_agents`. It needs an `ANTHROPIC_API_KEY` repository secret and
refuses to start when tasks × arms × repetitions exceeds `max_runs` (default 300). As a guide, Sonnet costs about
$0.05–0.10 per run on these tasks.

## Tokens by kind

`pipeline report` ends with a table per arm (also `pipeline tokens --runs FILE ...` for any runs file). Price differs by
kind, so the kinds explain a cost difference that total tokens do not:

| Column | Meaning |
|---|---|
| input | uncached input tokens |
| cache write | context written to the prompt cache: on first use, and again after a miss or an expiry (the context "refreshed") |
| cache read | context served from the cache, the cheapest kind |
| output, thinking | generated tokens; thinking is included in output |
| initial ctx | context given to the first model call: system prompt, tool definitions, task and pack |
| peak ctx | the largest context any model call was given |
| context | input + cache write + cache read, the context processed over the whole run |

Runs recorded before these fields existed (the paper's) show input and cache writes as one column.

## Rules that keep the comparison fair

- **The same model in every arm**, and every arm of a repository in **one shuffled session**: the plain arm's cost
  alone moved 39% between sessions on identical tasks in the study.
- **Pinned commits.** The graph, the tasks and the checkout are all at the entry's commit; the harness refuses to run
  when they differ.
- **Never tune on benchmark tasks.** Fix devkb from what the pack check or a run reveals, then measure on a new seed
  or a new repository, and say which runs came before and after a fix.
- **Report everything**: arms that cost more, tasks the graph got wrong, runs that failed.

## Permission denials (#369)

A refused command costs the agent a turn and a retry in whichever arm it falls, so it is noise in the cost columns.
The 0.2.14 re-run had 1.6 refusals per run; the 72 runs of #337's experiment and #382, #383, #367 had 3.9 (280).

**Why they were refused.** Every refused call carries the session's reason in its `tool_result`, so the causes come
from the runs themselves: `bench/policy/probes/denial_reasons.py RUN_DIRS` groups them (for "contains multiple
operations ... the following part requires approval: X", by the parts it names):

| Refusals | Reason (the session's) | Example |
|---|---|---|
| 76 | code with braces and quotes in the command ("brace with quote character") | `cat > t.py <<'E'` with a dict literal; `python3 - <<'E'` that rewrites a file |
| 67 | a path outside the checkout ("may only list files in the allowed working directories", a part with `..`, `/tmp`, `~/`) | `ls ..`, `ls ~/.cache/devkb/policy-work`, `cat > /tmp/x.py` |
| 44 | `sed -i` with a script the checker will not pass ("sed command requires approval", a `sed -i` part) | `sed -i 's/f(x)/f(x) if g(\"y\") else None/' a.py` |
| 30 | `cd`, then git (11) or a redirect or a write (19) ("cannot automatically determine the final working directory") | `cd <checkout>; git status`, `cd <checkout>; cat >> tests/t.py <<'E'` |
| 24 | a variable or a `NAME=value` prefix ("a variable in this command can't be checked before it runs") | `R=$PWD; $R/.venv/bin/python ...`, `PYTHONPATH=. .venv/bin/python ...` |
| 13 | devkb in a no-devkb arm (the deny list, #335): by design, not a form problem | `.venv/bin/devkb build --project corpus/fmt` in `none` |
| 9 | `$(...)`, a subshell or a loop | `(cd corpus/fmt && ...)`, `for f in ...; do` |
| 17 | other ("backslash-escaped whitespace", "can't be checked before it runs", "parser skipped input") | |

Without the 13 by design: 267, 3.7 per run. A headless probe (`bench/policy/probes/permission_probe.py`: one
`claude -p` per command form, with the benchmark's own `--allowedTools`, `--disallowedTools`, `--permission-mode` and
setting sources, in a scratch checkout) confirmed the larger groups on minimal forms (`ls ..`, `echo {a,b}`, a heredoc
with `{"a": 1}`, `R=...`, `$(...)`, a subshell, a loop and the venv by its absolute path were refused; `cd sub && ls`,
pipes, `;`, a heredoc without braces and a simple `sed -i 's/x/y/'` were not). Five forms were run three times with the
same answer (`ls ..`, `echo {a,b}`, the heredoc with `{"a": 1}`, a loop, a plain heredoc); the others once. Simple forms understate the checks: a `sed -i` or a `cd` the probe passed is
refused in the runs once its script holds quotes and parentheses, or once a git command or a write follows it.

**The fix**, the same for every arm: a paragraph in both prompts (`COMMANDS` in `bench/policy/storybench.py`), one
clause per group above: do not `cd` first; stay inside the checkout, scratch files too; no variables or `NAME=value`
prefixes, loops, `$(...)` or subshells; call the venv as `.venv/bin/python`; create and change files with the Write
and Edit tools, not `sed -i`, heredocs or Python one-offs. It says pipes and `;` are fine, since they were not refused.
No allow rule was added: apart from the absolute venv path (which `Bash(.venv/bin/python:*)` does not match, and
which the prompt now names), the refusals come from the session's command checks, which an allow rule does not lift.
**Re-run with the paragraph** (the 8 tickets of the 0.2.14 re-run, #301-#307 and #331, one run per arm, each at its own
base; rows in `bench/results/2026-11-20-denials-369/rerun-rows.jsonl`): 6 refusals in 16 runs. Two are the guardrail
answering a Grep in the devkb arm, which Claude Code records as a denial (a hook deny that carries devkb's answer, by
design); the other 4 are **0.25 per run**, 2 in each arm (0.2.14 re-run on the same tickets, counted the same way:
1.56 per run): two heredocs with braces and quotes, a redirect the checker could not read, and one other. Counted as
the issue counts them (every recorded denial), the re-run has 0.375 per run, 0.5 in `main`: the 0.3 target holds only
when the guardrail's substitutes are left out. The owner's decision (2026-11-20): the target counts refused command
forms, so the guardrail's substitutes and the no-devkb arms' devkb denials are left out; on that count it is met. Each run's `arm.json` records the prompt's
and the paragraph's SHA-256 (`prompt_sha256`, `commands_sha256`). Hidden checks 8/8 (`none`) and 7/8
(`main`), suites 16/16.

`claude_cmd()` in `policybench.py` builds every run's command; `tests/test_bench_same_permissions_369.py` builds it for
every arm and checks that only the no-devkb arms' devkb deny differs. Known limits: the story bench
(`storybench.run_one`, #117) builds its own command and has no `--setting-sources`; devkb's own `AGENTS.md` (kept in
the devkb arms) points at `~/.cache/devkb/cpp-corpus`, outside the checkout.

## The registry today

Every pack in the registry scores 1.0 against the truth at the pinned commits (55 tasks, 2026-11-14).

| id | kind | size | why it is here |
|---|---|---|---|
| `devkb` | cli | small | devkb measured on itself (4 tasks) |
| `lattice-scan` | cli | small | the first outside product to use devkb (12 tasks) |
| `click` | cli | small | a widely used command-line library (3 tasks: few module-level functions) |
| `lnbits` | web | medium | a FastAPI application (12 tasks) |
| `prefect` | web | large | a large FastAPI server and library (9 tasks) |
| `dispatch`, `mealie` | web | large, medium | the paper's two public replication repositories (8 and 7 tasks) |

Repositories built almost entirely from classes (for example `encode/httpx`) yield no task: both generators pick module-level
functions, because their truth resolves calls by import path and does not follow methods through untyped objects.

## What the truth sees

Calls resolved through the caller's imports, to module-level functions; `self.x()` / `cls.x()` to methods of the same
class in the same file; route handlers that reach a function through other handlers of their class. A raised message
is the first positional string or a `detail=` / `message=` / `msg=` / `description=` keyword. Calls on any other object
are not attributed, and a task is built only where the truth sees every caller. Migration files count as callers.

## How many runs a claim needs (#368; the numbers were confirmed by the owner on 2026-11-22)

At one run per cell, the sign of devkb's effect flipped from ticket to ticket in 0.2.14 (#334 +60%, #335 -33%, #287 -35%, #331 -47%): that is run-to-run spread, and the table
printed it without saying so. The tables now print each cell's number of runs and the coefficient of variation (CV) of its cost, and say so when a difference is read at
too few runs.

| | Rule (constants in `bench/policy/release_table.py`; confirmed 7 / 40% / 6) |
|---|---|
| a per-ticket claim | at least **7 runs per arm** (`MIN_RUNS_PER_ARM`) |
| the two-arm step of a ticket (3 runs) | names a direction only when the effect is larger than **40%** (`LARGE_EFFECT`); smaller differences are printed `(below n: 7 runs per arm ...)` |
| a release claim | pools at least **6 tickets** at 3 runs per arm (`MIN_POOLED_TICKETS`), with a paired interval; fewer is printed as `below n for a release claim` |

Runs needed per arm to see an effect at alpha 0.05 and power 0.8, from the CV (normal approximation, `n = 15.7 * CV^2 / effect^2`: a rule of thumb, not a model of these data):

| effect | 0.2.14 baseline, median CV 0.16 (16 cells, 3 runs each) | 0.2.15 batches, median CV 0.105 (22 cells: #399/#400 at 3 runs, yaml-cpp at 5) | the same, at the noisiest cell (CV 0.29) |
|---|---|---|---|
| 40% | 3 | 2 | 9 |
| 25% | 7 | 3 | 22 |
| 15% | 18 | 8 | 61 |

Reading it: the 0.2.15 cells are quieter than 0.2.14's (the harness fixes of #301 to #307 and #331 removed some of the noise), which would allow fewer runs; the spread across cells
(CV 0.03 to 0.29) is wide, so a rule sized to the median under-powers the noisy tickets. The confirmed 7 sits between the two. The owner decides the n because it sets the cost of every ticket
(one run is $0.10 to $0.50); change the three constants to apply a different one.

Baseline command (0.2.14): `python3 -c "import json,glob,statistics as s,collections as C;g=C.defaultdict(list);[g[(r['run'][1:4],r['arm'])].append(r['cost']) for f in glob.glob('bench/policy/results-3*.jsonl') for r in map(json.loads,open(f)) if r.get('cost') is not None and r['arm'] in('main','none')];print(s.median(s.stdev(v)/s.mean(v) for v in g.values() if len(v)==3))"` prints 0.163.

## Release performance check

`python bench/perf_release.py OLD_TAG NEW_TAG NAME=PATH ...` (for example `v0.2.12 v0.2.13 click=~/repos/click`) unpacks both tags, runs `bench/perf.py` as NEW, OLD, then NEW again, records the load before each pass (and waits until it is under `--max-load`, flagging a pass that starts above it), refuses a work directory on tmpfs, and writes `compare.md`: each change is marked *within noise* when it is no larger than the gap between the two NEW passes (#224).
