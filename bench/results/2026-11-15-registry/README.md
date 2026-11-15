# Benchmark: every repository in the registry, 2026-11-15

The six registry repositories not measured before (`bench/repos.yaml`: devkb, click, Mealie, Netflix Dispatch, lnbits,
Prefect), each at its pinned commit, run with the same pipeline, arms and protocol as the lattice-scan run of
2026-11-14 (`../2026-11-14-lattice-scan/`), and pooled with it. Exploratory, not pre-registered: the hypothesis labels
in `report-all.json` (H1–H4) are the paper's analysis applied to these runs, not new confirmatory tests.

## Setup

- **Tasks**: generated from source at each pinned commit, never from the graph (`pipeline prepare`): `cli_tasks.py`
  for devkb and click (error traces and refactor scopes), `confirm_tasks.py` for the web repositories (error to route
  handler, impact on route handlers, refactor scope). Every pack scored 1.0 against the truth before any run
  (`<repo>/pack-check.json`).
- **Arms**: `plain` (search and read), `core` (24 devkb tools), `lean` (7 tools), `pack` (a pre-computed pack in the
  prompt, no tools).
- **Protocol**: Sonnet in every arm, 5 repetitions, every arm of a repository in one shuffled session, a discarded
  warm-up per arm, 40-turn cap. 860 new runs, all valid, $61.89; with lattice-scan, 1,100 runs over 55 tasks, $74.49.
- **devkb and click got refactor tasks only**: the error-trace generator found no task meeting its selection rules in
  either. It was not changed to produce some (that would tune the task set); those two repositories measure only the
  one-hop case.

## Results, all seven repositories pooled

Cost saved against plain (positive is cheaper) and quality difference, 95% bootstrap intervals resampling runs within
task; Wilcoxon signed-rank over the 55 tasks, Holm-corrected (`report-all.json`):

| Arm | Median cost per run | Cost saved | Quality difference | Mean score | p (Holm) |
|---|---|---|---|---|---|
| plain | $0.0766 | — | — | 0.915 | — |
| core | $0.0616 | +9% [+4, +14] | +0.019 [+0.011, +0.027] | 0.934 | 0.15 (unadjusted) |
| lean | $0.0430 | +28% [+23, +33] | +0.034 [+0.027, +0.042] | 0.949 | 0.0008 |
| pack | $0.0255 | **+56%** [+51, +60] | **+0.051** [+0.044, +0.059] | 0.967 | 2e-8 |

No arm is worse than plain on quality (every lower bound is above zero).

By task kind (pooled; tasks per kind in brackets):

| Task kind | core | lean | pack |
|---|---|---|---|
| error trace, CLI (4) | +24% / +0.063 | +47% / +0.152 | +60% / +0.172 |
| error to route handler (6) | +21% / +0.027 | +54% / +0.056 | **+78%** / +0.086 |
| impact on route handlers (16) | +16% / +0.033 | +30% / +0.050 | **+68%** / +0.078 |
| refactor scope (29) | **−17%** [−32, −4] / +0.003 | 0% [−14, +12] / +0.005 | +19% [+7, +30] / +0.013 |

Per repository (`<repo>/report.json`):

| Repository | Runs | Tasks | Spent | Plain score | core | lean | pack |
|---|---|---|---|---|---|---|---|
| lattice-scan | 240 | 12 | $12.60 | 0.909 | +13% [+2, +23] / +0.022 | +36% [+27, +45] / +0.052 | +51% [+43, +59] / +0.058 |
| devkb | 80 | 4 | $3.50 | 0.993 | −20% [−60, +9] / +0.006 | +1% [−35, +26] / +0.004 | +40% [+14, +60] / +0.004 |
| click | 60 | 3 | $1.62 | 1.000 | −44% [−146, +11] / 0 | −3% [−88, +43] / 0 | −19% [−110, +31] / 0 |
| Mealie | 140 | 7 | $8.16 | 0.866 | 0% [−24, +19] / +0.065 | +17% [−6, +35] / +0.090 | +38% [+16, +55] / +0.053 |
| Dispatch | 160 | 8 | $11.15 | 0.915 | +26% [+14, +37] / +0.015 | +45% [+34, +55] / +0.040 | +61% [+52, +69] / +0.081 |
| lnbits | 240 | 12 | $16.21 | 0.905 | +20% [+10, +29] / +0.011 | +47% [+39, +54] / +0.030 | +63% [+54, +71] / +0.057 |
| Prefect | 180 | 9 | $21.26 | 0.913 | −5% [−16, +5] / +0.006 | +3% [−9, +13] / −0.006 | +61% [+53, +68] / +0.046 |

Tokens by kind, median run, all 1,100 runs (lattice-scan's runs predate the separate input and cache-write fields, so
the combined table shows them as one column):

| Arm | Turns | Input + cache write | Cache read | Output | Context processed | Context saved |
|---|---|---|---|---|---|---|
| plain | 6 | 8,538 | 151,305 | 1,638 | 163,586 | — |
| core | 7 | 5,162 | 180,267 | 1,868 | 185,267 | −5% |
| lean | 6 | 2,447 | 155,379 | 1,449 | 158,446 | +17% |
| pack | 3 | 1,259 | 73,720 | 943 | 77,020 | +57% |

Per task, score parts and the graph tools each arm called: `<repo>/detail.md`.

## Reading

- **Packs are the consistent result**: cheaper and better on every repository with chain tasks (38–63%), 56% pooled.
  The saving is where the answer is a chain: 68–78% on route-handler tasks, 60% on error traces, 19% on one-hop
  refactor scopes.
- **Tools pay off on chains and cost extra on one-hop work.** The 24-tool set is 17% dearer than plain on refactor
  scopes; the 7-tool set breaks even there and saves 30–54% on chains.
- **Size matters for the tool arms**: on Prefect, the largest repository, lean saved nothing (+3%, interval crossing
  zero, quality −0.006) while the pack still saved 61%. Why is not
  established by these runs; `prefect/detail.md` has the per-task turns and tool calls.
- **Where plain is already perfect, the graph can only add overhead**: click (3 refactor tasks, plain 1.000) and devkb
  (plain 0.993). click's intervals are too wide to conclude anything.
- **Limits**: one model; 55 tasks of which 10 are error-to-handler or error-trace tasks and only one each on Prefect
  and Dispatch; task generators shared with the graph's authors; exploratory.

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

`<repo>/runs.jsonl` is the raw output with answers (the `project` field holds the repository id in place of the local
checkout path); `<repo>/tasks.packs.json` holds the tasks, truth and packs.
