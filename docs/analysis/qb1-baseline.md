# QB1 baseline: which tests does each method name for a change? (2026-11-21)

Design: `docs/specs/quality-benchmarks.md`. Tool: `bench/quality/qb1_tests.py` (snapshot, items, score). No model runs.

## Setup
Three snapshots of `origin/main` (`632f8d0`, `ea9d037`, `215c505`). At each: a worktree, the graph built by that commit's own
devkb, and one full-suite run with a coverage context per test (`pytest --cov --cov-context=test`, 8 workers). Items are the
next merged PRs (first-parent commits, up to 12 after the snapshot) that change a function present at the snapshot: 13 items,
1-4 changed functions each. **Truth** = test files whose coverage context executed a body line of a changed function at the
snapshot (median 22 files per item). No test covers more than 30% of the code, so the "wide test" filter removed nothing.
Predictions are made at the snapshot, up to 12 commits behind the change, as an agent working there would have them.

## Result (13 items; recall of the covering test files; the 90% interval is a bootstrap over items). Re-run and corrected 2026-11-21
After an independent audit: predictions count only real test files (`tests/test_*.py`; `conftest.py` and helper modules can never be
in the truth, which understated `pack file` precision by about 0.04), and the three coverage runs were repeated with the pytest outcome
recorded (`health`): every test file ran, none failed to collect or was skipped, the 42 files at the last snapshot with no `devkb/`
coverage passed and exercise other code (the benchmark harness, scripts), and the recall figures reproduced exactly.

| arm | files named (median) | recall | missed-guard | precision |
|---|---|---|---|---|
| `pack file` (devkb) | 24 | **0.73** (0.66-0.80) | 0 of 13 | 0.64 |
| `pack refactor` per function | 0 | 0.12 (0.04-0.20) | 7 of 13 | 1.00 |
| tests that import the module | 22 | 0.69 (0.62-0.76) | 0 of 13 | 0.65 |
| tests named after the module | 0 | 0.05 (0.02-0.08) | 7 of 13 | 0.94 |
| tests that mention a changed function's name | 30 | 0.72 (0.56-0.86) | 1 of 13 | 0.48 |
| union of `pack file`, import and grep | | 0.90 | | |

Per snapshot (5, 5 and 3 items), `pack file` / import / grep: 632f8d0 0.80 / 0.75 / 0.81; ea9d037 0.67 / 0.63 / 0.69; 215c505 0.72 / 0.69 / 0.64.
Paired differences in recall, 90% over items: `pack file` - import **+0.04 (0.00 to +0.08)**, the same +0.04 with any one snapshot left out;
`pack file` - grep +0.01 (-0.15 to +0.18). The 13 items cluster in 3 snapshots and some share changed functions, so these intervals are a
floor on the spread.

## Reading
- **The gate fails.** The design asked for recall 15 points above the best baseline; `pack file` is 1 point above grep and 4
  above the import search, a small and consistent edge over import (+0.04 in every leave-one-snapshot-out case) but nowhere near 15.
- **There is headroom.** The three methods together reach 0.90, so 0.73 is not a ceiling, and 40% of what `pack file` lists
  does not cover the change (precision 0.64).
- **Why `pack file` misses (corrected after an independent audit).** 73 of the 266 covering tests are not named. 36 of those
  mention the changed function's name in their text, but that count is inflated: it counts the same few test files once per item
  (`test_boundaries`, `test_language_profiles`, `test_devkb_cpp_calls_dkb003` recur across the `Packer.refactor` and
  `Packer.change` items) and it includes name collisions (`S.build(...)`, `P.build(...)` call a test helper's own `build`;
  `test_inventory.extract(...)` is another module's `extract`; `Path(__file__).resolve()` matches `ReadTools.resolve`). The
  genuine "call through a receiver variable" cases come to about **8 distinct (test file, function) pairs** (`packer.refactor`,
  `packer.change`, `api._coverage`, `p.change`), mostly from tuple-unpacking a helper's result (`api, packer = P.api(...)`),
  not 22 of 73. Earlier text claimed 30% of the misses were one gap and that 10 were "through the CLI or a subprocess"; the
  second claim is unsupported (the coverage run does not measure child processes) and both are withdrawn.
- **`pack refactor` is not the tool for this question**: it lists the files with a direct caller, which for a function called
  by its own tests is few, and it silently names none in 7 of 13 items.

## Decision (the loop in `docs/analysis/improvement-plan-data-loop.md`)
The one change this suggests is small: attribute a Python call `x.name(...)` when `x` came from tuple-unpacking a helper that
returns constructed objects. With about 8 distinct pairs behind it the expected gain is about 2 points of recall, so it is no
longer a route to the 0.84 gate (the import baseline plus 15 points). It is kept as a correctness item, not a QB1 lever. The open
questions are the benchmark's own: the precision correction below, a cluster bootstrap, and whether every test file missing from
the coverage truth really runs no `devkb/` code (42 of 113 at the last snapshot; 13 import the harness, 27 unexplained).

## Limits
13 items from 3 snapshots is a baseline, not a verdict; the interval is wide (grep: 0.56-0.86). File-level truth; coverage
counts a test that executes the function incidentally. Snapshots are 0-12 commits behind. One test file was left out of the
coverage run (`test_bench_user_policy_366.py`, which needs the harness). The worktrees stay in `~/.cache/devkb/qb1/` for re-runs
(`git worktree prune` removes their entries).
