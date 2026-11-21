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
The 0.2.14 re-run had 1.6 denials per run; the 72 runs of #337's experiment and #382, #383, #367 had 3.9 (280).

**How they were found.** `bench/policy/probes/permission_probe.py` runs one headless `claude -p` per command form, with
the benchmark's own `--allowedTools`/`--disallowedTools`, `--permission-mode acceptEdits` and setting sources, in a
scratch git checkout, and records whether the session refused it. Each form was probed three times; the answer was
the same every time. Denied commands from the runs, replayed verbatim (the checkout path rewritten), were refused
again, so the probe reproduces the runs.

| Form | Refused | Example |
|---|---|---|
| a path outside the checkout | yes | `ls ..`, `ls /home/...`, `cd /tmp/x && ...` |
| a shell loop | yes | `for f in a b; do echo $f; done` |
| a variable | yes | `R=$PWD; ls $R` |
| command substitution | yes | `ls $(pwd)/sub` |
| a subshell | yes | `(cd sub && ls)` |
| a brace group with a quoted string (Python dict literals in a heredoc) | yes | `cat > f.py <<'E'` with `{"a": 1}`; `echo {a,b}` |
| the venv by its absolute path | yes | `/abs/checkout/.venv/bin/python -c ...` |
| `cd` inside the checkout, then a command | no | `cd <checkout> && ls`, `cd sub && ls` |
| a heredoc without braces, a redirect into the checkout, `sed -i` | no | `python3 - <<'E'`, `echo hi > sub/y.txt` |
| compound commands and pipes of allowed commands | no | `ls; ls sub`, `.venv/bin/python -c ... 2>&1 \| tail -1` |

So `cd` is not the cause, though most refused commands begin with it (149 of 280): what follows it is. Of the 280,
127 named a path outside the checkout, 10 each used a loop, a subshell or `$(...)`, 5 a variable and 3 the absolute
venv path; most of the rest were heredocs that write Python with dict literals.

**The fix**, the same for every arm: a paragraph in both prompts (`COMMANDS` in `bench/policy/storybench.py`) that
says to run one simple command or a short `&&` chain from the checkout root, without loops, variables, `$(...)` or
subshells, to call the venv as `.venv/bin/python`, to stay inside the checkout, and to create and change files with
the Write and Edit tools rather than heredocs. No allow rule was added: the refused forms are refused by the session's
command checks, not for a missing tool, and a broader rule would weaken the deny list. `permissions(arm)` in
`policybench.py` gives every arm the same allow list; `tests/test_bench_same_permissions_369.py` asserts it and the
shared prompt.

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

## Release performance check

`python bench/perf_release.py OLD_TAG NEW_TAG NAME=PATH ...` (for example `v0.2.12 v0.2.13 click=~/repos/click`) unpacks both tags, runs `bench/perf.py` as NEW, OLD, then NEW again, records the load before each pass (and waits until it is under `--max-load`, flagging a pass that starts above it), refuses a work directory on tmpfs, and writes `compare.md`: each change is marked *within noise* when it is no larger than the gap between the two NEW passes (#224).
