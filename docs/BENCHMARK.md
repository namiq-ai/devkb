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

## Run the agents (costs money)

Locally, with the Claude Code CLI installed and signed in:

```bash
.venv/bin/python -m devkb.bench.pipeline run <id> --arms plain,core,lean,pack --reps 5 --model sonnet
.venv/bin/python -m devkb.bench.pipeline report <id> --model sonnet
```

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

## The registry today

| id | kind | size | why it is here |
|---|---|---|---|
| `devkb` | cli | small | devkb measured on itself (4 tasks; packs 0.99) |
| `lattice-scan` | cli | small | the first outside product to use devkb (12 tasks; packs 1.0) |
| `click` | cli | small | a widely used command-line library (3 tasks: few module-level functions) |
| `lnbits` | web | medium | a FastAPI application (12 tasks; packs 0.96 against truth) |
| `prefect` | web | large | a large FastAPI server and library (10 tasks; packs 0.79: route-handler gaps to fix) |
| `dispatch`, `mealie` | web | large, medium | the paper's two public replication repositories |

Repositories built almost entirely from classes (for example `encode/httpx`) yield no task: both generators pick module-level
functions, because their truth resolves calls by import path and does not follow methods through untyped objects.
