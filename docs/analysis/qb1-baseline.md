# QB1 baseline: which tests does each method name for a change? (2026-11-21)

Design: `docs/specs/quality-benchmarks.md`. Tool: `bench/quality/qb1_tests.py` (snapshot, items, score). No model runs.

## Setup
Three snapshots of `origin/main` (`632f8d0`, `ea9d037`, `215c505`). At each: a worktree, the graph built by that commit's own
devkb, and one full-suite run with a coverage context per test (`pytest --cov --cov-context=test`, 8 workers). Items are the
next merged PRs (first-parent commits, up to 12 after the snapshot) that change a function present at the snapshot: 13 items,
1-4 changed functions each. **Truth** = test files whose coverage context executed a body line of a changed function at the
snapshot (median 22 files per item). No test covers more than 30% of the code, so the "wide test" filter removed nothing.
Predictions are made at the snapshot, up to 12 commits behind the change, as an agent working there would have them.

## Result (13 items; recall of the covering test files; the 90% interval is a bootstrap over items)

| arm | files named (median) | recall | missed-guard | precision |
|---|---|---|---|---|
| `pack file` (devkb) | 26 | **0.73** (0.66-0.80) | 0 of 13 | 0.60 |
| `pack refactor` per function | 0 | 0.12 (0.04-0.20) | 7 of 13 | 1.00 |
| tests that import the module | 22 | 0.69 (0.62-0.76) | 0 of 13 | 0.65 |
| tests named after the module | 0 | 0.05 (0.02-0.08) | 7 of 13 | 0.94 |
| tests that mention a changed function's name | 30 | 0.72 (0.56-0.86) | 1 of 13 | 0.48 |
| union of `pack file`, import and grep | | 0.90 | | |
| `pack file` plus import | | 0.76 | | |

Missed-guard = an item where the arm named none of the covering tests.

## Reading
- **The gate fails.** The design asked for recall 15 points above the best baseline; `pack file` is 1 point above grep and 4
  above the import search, inside each other's intervals. On this measure the graph does not yet beat a one-line grep.
- **There is headroom.** The three methods together reach 0.90, so 0.73 is not a ceiling, and 40% of what `pack file` lists
  does not cover the change (precision 0.60).
- **Why `pack file` misses.** 73 of the 266 covering tests are not named. Of those, **36 name the changed function in their own
  text**. For 35 of them I classified the call: 22 are a call on a variable or module alias (`packer.refactor(...)`,
  `S.build(...)`, `test_inventory.extract(...)`), 5 pass the name as a string (`refactor("name")`, `api.call("symbol", ...)`),
  1 is a call on a constructed object, 7 are other mentions. A further 25 are reached indirectly and 10 through the CLI or a subprocess.
  So about 22 of 73 (30%) are one gap: Python calls through a receiver variable or an import alias are not attributed. It is
  the Python counterpart of what #120 did for C++ (typed receivers).
- **`pack refactor` is not the tool for this question**: it lists the files with a direct caller, which for a function called
  by its own tests is few, and it silently names none in 7 of 13 items.

## Decision (the loop in `docs/analysis/improvement-plan-data-loop.md`)
Iterate once. Change: resolve a Python call `x.name(...)` when `x` is bound in the same scope to a constructor call or an
import of a module in the repository (the C++ typed-receiver approach, applied to Python). Gate: re-run this benchmark on the
same 13 items and, to avoid tuning on them, on a fourth snapshot never scored; pass when recall is at least 0.84 (the import
baseline plus 15 points) with precision not below 0.55. Fail again: park the Python receiver work and report the ceiling.

## Limits
13 items from 3 snapshots is a baseline, not a verdict; the interval is wide (grep: 0.56-0.86). File-level truth; coverage
counts a test that executes the function incidentally. Snapshots are 0-12 commits behind. One test file was left out of the
coverage run (`test_bench_user_policy_366.py`, which needs the harness). The worktrees stay in `~/.cache/devkb/qb1/` for re-runs
(`git worktree prune` removes their entries).
