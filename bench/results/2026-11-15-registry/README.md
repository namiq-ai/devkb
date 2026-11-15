# Benchmark: every repository in the registry, 2026-11-15

The six registry repositories not measured before (`bench/repos.yaml`: devkb, click, Mealie, Netflix Dispatch, lnbits,
Prefect), each at its pinned commit, run with the same pipeline, arms and protocol as the lattice-scan run of
2026-11-14 (`../2026-11-14-lattice-scan/`), and pooled with it. Exploratory, not pre-registered: the hypothesis labels
in `report-all.json` (H1–H4) are the paper's analysis applied to these runs, not new confirmatory tests.

**Corrected on 2026-11-15** (see [Corrections](#corrections)): Prefect's first session ran its tool arms without
tools, and four tasks had a truth that missed callers. The numbers below are the corrected ones.

## Setup

- **Tasks**: generated from source at each pinned commit, never from the graph (`pipeline prepare`): `cli_tasks.py`
  for devkb and click (error traces and refactor scopes), `confirm_tasks.py` for the web repositories (error to route
  handler, impact on route handlers, refactor scope). Every pack scored 1.0 against the truth before any run
  (`<repo>/pack-check.json`).
- **Arms**: `plain` (search and read), `core` (12 single-question devkb tools), `lean` (7 tools), `pack` (a pre-computed pack in the
  prompt, no tools).
- **Protocol**: Sonnet in every arm, 5 repetitions, every arm of a repository in one shuffled session, a discarded
  warm-up per arm, 40-turn cap.
- **devkb and click got refactor tasks only**: the error-trace generator found no task meeting its selection rules in
  either. It was not changed to produce some (that would tune the task set); those two repositories measure only the
  one-hop case.

## Results, all seven repositories pooled

1,038 runs over 52 tasks (the three tasks whose truth was wrong are excluded here and reported in the addendum),
$66.28. Cost saved against plain (positive is cheaper) and quality difference, 95% bootstrap intervals resampling runs
within task; Wilcoxon signed-rank over the 52 tasks, Holm-corrected (`report-all.json`):

| Arm | Median cost per run | Cost saved | Quality difference | Mean score | p (Holm) |
|---|---|---|---|---|---|
| plain | $0.0755 | — | — | 0.928 | — |
| core | $0.0605 | +19% [+13, +23] | +0.023 [+0.015, +0.031] | 0.951 | 0.010 (unadjusted) |
| lean | $0.0417 | +39% [+34, +43] | +0.033 [+0.025, +0.040] | 0.961 | 3e-5 |
| pack | $0.0264 | **+56%** [+52, +60] | **+0.051** [+0.043, +0.059] | 0.979 | 3e-8 |

No arm is worse than plain on quality (every lower bound is above zero).

By task kind (pooled; tasks per kind in brackets):

| Task kind | core | lean | pack |
|---|---|---|---|
| error trace, CLI (4) | +24% / +0.063 | +47% / +0.152 | +60% / +0.172 |
| error to route handler (6) | +30% / +0.013 | +58% / +0.054 | **+77%** / +0.075 |
| impact on route handlers (15) | +32% / +0.052 | +50% / +0.051 | **+66%** / +0.088 |
| refactor scope (27) | **−17%** [−33, −3] / +0.003 | +2% [−12, +15] / −0.001 | +21% [+8, +32] / +0.007 |

Per repository (`<repo>/report.json`; lnbits and Mealie without their wrong-truth tasks):

| Repository | Runs | Tasks | Spent | Plain score | core | lean | pack |
|---|---|---|---|---|---|---|---|
| lattice-scan | 240 | 12 | $12.60 | 0.909 | +13% [+2, +23] / +0.022 | +36% [+27, +45] / +0.052 | +51% [+43, +59] / +0.058 |
| devkb | 80 | 4 | $3.50 | 0.993 | −20% [−60, +9] / +0.006 | +1% [−35, +26] / +0.004 | +40% [+14, +60] / +0.004 |
| click | 60 | 3 | $1.62 | 1.000 | −44% [−146, +11] / 0 | −3% [−88, +43] / 0 | −19% [−110, +31] / 0 |
| Mealie | 120 | 6 | $7.35 | 0.853 | +3% [−21, +22] / +0.076 | +18% [−5, +36] / +0.095 | +42% [+20, +60] / +0.062 |
| Dispatch | 160 | 8 | $11.15 | 0.915 | +26% [+14, +37] / +0.015 | +45% [+34, +55] / +0.040 | +61% [+52, +69] / +0.081 |
| lnbits | 200 | 10 | $12.85 | 0.941 | +23% [+13, +33] / +0.011 | +53% [+45, +60] / +0.032 | +66% [+56, +74] / +0.049 |
| Prefect | 178 | 9 | $17.22 | 0.947 | +28% [+17, +37] / +0.025 | +41% [+31, +50] / −0.017 | +59% [+51, +66] / +0.047 |

Tokens by kind, median run, the 1,038 runs (lattice-scan's runs predate the separate input and cache-write fields, so
the combined table shows them as one column):

| Arm | Turns | Input + cache write | Cache read | Output | Context processed | Context saved |
|---|---|---|---|---|---|---|
| plain | 5.5 | 9,188 | 154,584 | 1,608 | 164,482 | — |
| core | 7 | 4,654 | 172,816 | 1,839 | 187,362 | 0% |
| lean | 6 | 2,184 | 146,214 | 1,338 | 156,170 | +25% |
| pack | 3 | 1,388 | 76,162 | 914 | 77,330 | +56% |

Per task, score parts and the graph tools each arm called: `<repo>/detail.md`.

## Reading

- **Packs are the consistent result**: cheaper and better on every repository with chain tasks (42–66%), 56% pooled.
  The saving is where the answer is a chain: 66–77% on route-handler tasks, 60% on error traces, 21% on one-hop
  refactor scopes.
- **Tools pay off on chains and cost extra on one-hop work.** The 12-tool set is 17% dearer than plain on refactor
  scopes and 30–32% cheaper on route-handler chains; the 7-tool set breaks even on refactors and saves 47–58% on
  chains.
- **Prefect, the largest repository, behaves like the others** once its tool arms have tools: lean 41% cheaper,
  core 28%. Its lean quality is the one negative point estimate (−0.017 [−0.041, +0.003], inside the 0.05
  non-inferiority margin), mostly one impact task (`_sync_automation_related_resources`, 0.76) where lean agents
  stopped after a median of three turns.
- **Where plain is already perfect, the graph can only add overhead**: click (3 refactor tasks, plain 1.000) and devkb
  (plain 0.993). click's intervals are too wide to conclude anything.
- **Limits**: one model; 52 tasks of which 10 are error-to-handler or error-trace tasks; task generators written by
  the graph's authors (an independent truth check now runs before every run, below); exploratory.

## Corrections

Found while investigating why every arm scored 0.56–0.67 on lnbits `get_wallet` although its pack checked at 1.0.

1. **Prefect's tool arms had no tools** in the first session: the graph server is started with `uv` inside the
   checkout, and Prefect's own `required-version` setting made uv refuse to start, so all 90 core and lean runs were
   agents told to use tools they did not have. Nothing flagged it. That session first reported core −5% and lean +3%
   on Prefect, and pooled core +9%, lean +28%. Prefect was rerun whole in a new session (all four arms, the same nine
   tasks, packs from the fixed graph): `prefect/runs.jsonl`. The first session is kept in `prefect/superseded/`.
   Two lean runs of the rerun are excluded (178 of 180 kept): their graph server started during 12 seconds in which
   the working copy held older devkb code.
2. **Four truths missed callers** that the graph also missed, so the pack check could not see it: package re-exports
   (lnbits `get_wallet`, 22 of 39 caller files; `clear_wallet_cache`, one handler and two test files), dotted module
   paths (Prefect `read_flow_run`, 10 of 19) and calls at import time (Mealie `get_app_dirs`, 3 of 14). Agents who
   found the real callers were marked down. Prefect's rerun uses the corrected truth; the other three tasks are
   excluded from the pooled numbers above and were rerun in their own sessions (addendum). The other 51 tasks' truths
   are unchanged under the corrected rules.
3. The fixes: devkb's graph and the truth follow re-exports, dotted module paths and import-time calls;
   `bench/truth_check.py`, an independent implementation, now gates `prepare`; the harness makes a tool-arm run
   invalid when its graph server did not connect, starts it with `uv --no-config`, stores whole answers (they were
   cut at 1,500 characters, so the original runs cannot be rescored), and `pipeline report` fails when a tool arm never
   called the graph.

Before the corrections, pooled over 55 tasks: pack +56%, lean +28%, core +9%. The pack result did not move; the tool
arms' savings were understated because one repository's tool arms were measured without tools.

## Addendum: the three corrected tasks

Rerun with the corrected truth and packs from the fixed graph, all four arms, 5 repetitions, one session per
repository (`addendum/`, 60 runs, all valid, every tool-arm run connected). Every arm now scores 0.97–1.00:

| Task | plain | core | lean | pack |
|---|---|---|---|---|
| lnbits `clear_wallet_cache` (impact) | $0.086 / 0.97 | $0.050 / 0.98 | $0.059 / 0.99 | $0.006 / 1.00 |
| lnbits `get_wallet` (refactor) | $0.091 / 1.00 | $0.097 / 1.00 | $0.105 / 1.00 | $0.036 / 1.00 |
| Mealie `get_app_dirs` (refactor) | $0.024 / 1.00 | $0.026 / 1.00 | $0.016 / 1.00 | $0.016 / 1.00 |

(median cost / mean score). Under the old truth the same tasks scored 0.56–0.96. `addendum/invalid/` keeps two failed
attempts, reported and not used: one whose graph server never started (a relative path), one blocked like Prefect's.

## Reproduce

```bash
for r in devkb click mealie dispatch lnbits prefect; do
  .venv/bin/python -m devkb.bench.pipeline prepare $r
  .venv/bin/python -m devkb.bench.pipeline run $r --arms plain,core,lean,pack --reps 5 --model sonnet
  .venv/bin/python -m devkb.bench.pipeline report $r --model sonnet
done
# pooled: the analysis names each repository after its runs file
python3 study/analysis/analyze.py <dir>/{lattice-scan,devkb,click,mealie,dispatch,lnbits,prefect}.jsonl --model sonnet --out report-all.json
```

Re-preparing with today's code generates different task sets for some repositories (the selection rules count
callers, which the fixes changed); these results keep the tasks they were run on (`<repo>/tasks.packs.json`).
`<repo>/runs.jsonl` is the raw output with answers (the `project` field holds the repository id in place of the local
checkout path).
