# Hook-to-graph map with 0.2.15 data, and the root cause of the guide's errors (2026-11-23)

Data window: v0.2.14 tag (2026-11-20 01:59) to 2026-11-23. Sources: `~/.claude/hooks/devkb-guardrail.log` (every session on this machine: working sessions and benchmark arms together, 2,111 decisions), `.devkb/process-api-telemetry.jsonl` (188 queries in the window), `docs/analysis/devkb-usage-0.2.15-by-period.md`, `docs/analysis/workflow-router-benchmark.md`.

## 1. What is wired, and what it reads from the graph

| # | Hook (event, matcher) | Wired where | Script | Graph read | Context given | Measured in 0.2.15 |
|---|---|---|---|---|---|---|
| H1 | SessionStart | plugin `hooks.json` only | `plugins/devkb/hooks/session-start.sh` | none read; **writes**: `devkb build` in the background when `HEAD != manifest.git_head` or no `nodes.jsonl`, behind a lock, 10 s hook timeout | none (build runs detached) | No per-hook data. Build times from this release's perf run: see release note. Zephyr full build 113.5 s |
| H2 | PreToolUse, `Edit\|Write\|MultiEdit\|NotebookEdit\|Bash` | plugin `hooks.json`, or `devkb init --claude-hook` | `devkb hook pre-edit` (`devkb/hook.py`) | `devkb pack file PATH`: functions other files call, dependents, tests to run, coverage Complete/Incomplete | up to 6,000 characters, once per file per session; never blocks | **No data.** This repository's `.claude/settings.json` does not wire it, so no working session or arm used it. Its value is unmeasured |
| H3 | PreToolUse, `Read\|Grep\|Bash` | this repo's `.claude/settings.json` (checkout script) **and** `~/.claude/settings.json` (an installed copy, below) | `scripts/devkb_guardrail.py` | per search intent: `symbol` / `symbol --source` (locate, read body), `uses` (call sites), `outline` (list symbols), `pack refactor` (the Complete/fresh check and the default question); freshness from `manifest.git_head` vs `git diff` of changed files | answer appended to the search result, or a reminder, or nothing | See table 2 |
| H4 | PostToolUse, `Grep\|Bash` | same two settings files | `scripts/devkb_guardrail_post.py` | none read; **writes** `.devkb/graph-misses.jsonl` when devkb could not answer and grep found code | 0 tokens | 23 misses in 23 groups at release, all `cannot-resolve` on names searched while the graph was older than the edits |
| H5 | UserPromptSubmit | opt-in; `prompt.sh` is **not** registered in `hooks.json` | `devkb hook context` (records the task's words so `symbol` breaks ties) or `devkb hook prompt` (router: `devkb/router.py`) | router: `read_tools` retrieval by route (`navigate`, `ticket`, `error`, `change`); context: none | router: at most about 3,000 characters; context: none | Router, 72 benchmark runs: no detectable effect, +0.8 turns and +13% cost against `rmain`; 41 of the 188 telemetry queries came from the router |
| - | Not a hook: CLI | the agent's shell | `devkb symbol\|uses\|outline\|pack\|tests_for` | any | any | 130 of 188 queries |
| - | Not a hook: MCP | `.mcp.json` (untracked here; the repo has none on purpose) | `devkb mcp --toolset lean-pack` | 3 tools loaded, 9 behind ToolSearch | schemas cost about 3k tokens per call when all are loaded | 17 MCP calls in P4 of the working sessions; 0 to 2 per arm in benchmarks |

**Two copies of the guardrail run in this repository.** `~/.claude/settings.json` points at `~/.claude/hooks/devkb-guardrail/` (installed 2026-11-19 from commit 3f56ece, "0.2.13 complete", 62,746 bytes) and the repository's `.claude/settings.json` points at the checkout's `scripts/devkb_guardrail.py` (95,634 bytes, 713 lines different). Claude Code runs hooks from both settings files. They share one log and one set of state files (`.devkb-guardrail-answers`, `.devkb-guardrail-pending`). Of 2,113 decision rows only 3 pairs repeat the same decision in the same second, so double decisions do not explain the data, but **the log does not say which copy wrote a row.** The earlier usage report said the checkout's script is what ran in working sessions; that was not established and is corrected here. Benchmark arms are unaffected (each arm runs its pinned commit).

### Table 2: what H3 did (all sessions, 2,111 decisions)

| Outcome | Count | Share | Graph question asked |
|---|---|---|---|
| pass-through, `not-complete` | 597 | 28% | `pack refactor` said Incomplete or could not prove the name |
| pass-through, `stale-graph` | 468 | 22% | built commit != HEAD and a changed file mentions the name |
| pass-through, `duplicate` | 238 | 11% | the same answer was already given this session |
| pass-through, `intent` | 199 | 9% | a regex, config key or text question the graph does not answer |
| pass-through, `cut` / `verdict` | 16 / 12 | 1% | answer cut by the search's own output limit / judged wrong |
| remind (no answer, the line naming a devkb command) | 415 | 20% | none |
| alongside (answer beside grep's output) | 98 | 5% | `pack refactor` 69, `uses` 17, `symbol` 8 |
| span-hint (line range for a file) | 41 | 2% | `outline` |
| teach / substitute / read-answer | 9 / 7 / 7 | 1% | `pack refactor` / `pack refactor` and `uses` / `symbol --source` |

By tool: Bash 1,784, Grep 298, Read 29. Intent of the searches: read-body 462, in-file 484, call-sites 446, locate 240, list-files 118, unknown 113 or more, count 29. Size of an answer when given: median 293 characters (n=140), maximum 2,260, against the guide's 800-token and 3,000-character ceilings.

**Answered share.** Answers given (alongside, substitute, read-answer) are 112 of 2,111 decisions, 5.3%; with span hints 7.2%. By period and session class see `devkb-usage-0.2.15-by-period.md`: 4.7% of decisions in working sessions, 7.8% in benchmark runs.

### Table 3: the queries themselves (188, median 37 ms, 90th percentile 67 ms, median reply 2,158 bytes)

| Tool | Count | Source | Count | Outcome | Count |
|---|---|---|---|---|---|
| pack | 114 | cli | 130 | complete | 97 |
| symbol | 54 | router | 41 | incomplete | 51 |
| tests_for | 10 | none recorded | 17 | ambiguous | 11 |
| outline | 5 | | | no-match | 9 |
| uses | 5 | | | none recorded | 17 |

Half of the packs came back Incomplete or ambiguous: that is the lever the hook has, and it is why `not-complete` leads the pass-through reasons.

## 2. Root cause of "Wrong or out of date" in the guide

Method: for each claim, find where the same text, number or command exists in the repository and when it was written.

| Guide claim | What is true | Where the guide's version came from | Root cause |
|---|---|---|---|
| `python3 -m devkb.hook session-start / pre-search / post-tool-telemetry / prompt-router` | `hook.py` takes `pre-edit`, `prompt`, `context`; SessionStart is a shell script (`session-start.sh`), search interception and its telemetry are two scripts under `scripts/` | The *roles* exist (session start, search guard, edit pack, router, post telemetry); `session-start` also appears in `devkb/startup.py` and `mcp_server.py` as a different thing (a role brief, ODSF-311) | **Names invented from roles.** The document was written from descriptions of the layers, not from `devkb/hook.py` or `.claude/settings.json`; a module path was made up for each layer |
| `python3 -m devkb.testing.hook_replay`, `tests/fixtures/hook_sessions.jsonl` | `bench/policy/hook_replay.py`, reading a run's `stream.jsonl`; no such fixture | `docs/analysis/hook-answer-rate-367.md` describes `hook_replay.py` and `stream.jsonl` | **Same cause, and a mix-up:** `stream.jsonl` is a benchmark run's recording of the agent session (replay *input*); the guide made it the hook's telemetry *output* ("Layer 7 logs to stream.jsonl"). The real output is `.devkb/graph-misses.jsonl` |
| `policybench.py score --run-dir bench/runs/latest/` | `score <ticket-number>` | none in the repo | **Not checked against `--help`** |
| Pass condition "Output MUST equal `NO CONTEXT`" | The router returns `None` when `DEVKB_ROUTER` is exactly `0`; nothing is printed | `docs/analysis/improvement-plan-data-loop.md:16`: a headless `claude -p` run where the model "said NO CONTEXT" | **A model's sentence read as program output** |
| Router `+2.6 turns, +$0.09` | +0.8 turns, +13% against `rmain` | `workflow-router-benchmark.md`, written 2026-11-20/21; §"Router effect" (line 206) corrects the +2.6, which compared against 12 discarded runs | **Read before the correction**, or read the headline without the later section |
| `1,231` tests | 1,506 on main | `improvement-plan-data-loop.md:103` and `workflow-router-benchmark.md:221`: 1,231 passed on `feat/workflow-router` on 2026-11-21 | **A snapshot of a branch two days and about 275 tests ago** |
| `.mcp.json` runs `python -m devkb.mcp_server` | That module has a `__main__` and runs. The repository tracks no `.mcp.json`, on purpose (`docs/analysis/devkb-none-mcp-cli.md`); a local untracked one uses `devkb mcp --toolset lean-pack` | the guide's own design, not a repository fact | **Prescription presented as description**: it states a configuration the repository decided against, without saying it differs |
| Recall `0.74 -> 0.83` | QB1: 0.74 (0.69 to 0.80) to 0.83 (0.77 to 0.88), precision 0.63 | `docs/analysis/qb1-baseline.md:62-63` | **Interval and precision dropped**, so a pointer reads as a settled gain |
| `Item #7`, `-250 tokens and -0.25 tool calls per run`, `-18% context`, `+0.15 held-out recall` | not found in the repository by text search (the held-out figure is in `improvement-plan-data-loop.md`, in another context) | unknown | **Unsourced figures**; I could not trace them |

### Why it happened (the process cause)

1. **Written from the analysis documents, not from the code that is wired.** Every correct statement in the guide is a conclusion from `docs/analysis/*`; every wrong one is wiring, a command, or a number a document later corrected. The documents are dated 2026-11-20/21 (router branch) and the repository moved after that (#401 merged, 0.2.15 chain).
2. **No verification step that executes the guide.** Its own checklist commands (`hook_replay --fixtures`, `score --run-dir`, `prompt-router`) fail when run. Nothing required running them before circulating.
3. **A snapshot with no date or commit.** The guide cites `1,231` tests and `feat/workflow-router` but not a commit, so it cannot be diffed against `main`.
4. **A sound design layered on a real system under different names.** Layers 1, 3, 5 and 7 correspond to real components; the document renamed them and filled in plausible interfaces. This is the hardest error to see by reading, because the behaviour described is mostly right.
5. **The same drift risk exists inside this repository**: my own usage report said the checkout's hook ran in working sessions, which the two-copies finding above shows was not established. The `.mcp.json` row of my first comparison was wrong in the same way (I did not check that the module runs or that the file is untracked).

### Prevention (becomes 0.2.16 ticket scope)

- A `tests/` check that every `python -m devkb.X` and every `scripts/...` path in `docs/` and `README.md` resolves (a command in a document must exist).
- Documents that state wiring carry the commit they were checked at, and a `make check-docs` that runs their commands in a scratch checkout.
- Record the guardrail's version (commit) in each log row, so a decision can be tied to the copy that wrote it, and resolve the two-copies question by either removing the user-level copy from this repository's sessions or tagging rows.
