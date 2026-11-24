# Hidden-location batches of 7 runs per arm: #386 and #418 (2026-11-22 to 2026-11-23)

Three arms per ticket, 7 runs each, the ticket's location withheld (`POLICY_HIDE_START=1`), one batch per ticket, model fixed, work directories under `~/.cache` (not `~/.claude`). Arms: `none` (no devkb), `main` (shell and hook), `bothuser` (shell, hook and the MCP tool entry point, a user's policy). These are the figures in the Execution-result comments of #386 and #418. Files: `results-N.jsonl` (one row per run), `runs-N.tgz` (each run's `stream.jsonl`, `score.json`, `arm.json`).

The repository's `bench/policy/results-386.jsonl` and `results-418.jsonl` hold only the earlier 6-row batches; these 21-row files are the 7-run experiment. At 7 runs per arm no difference below is distinguishable from noise.


## #386

| Arm | Runs | Acceptance | Suite | Turns | Cost per run | Context at first call | devkb queries | Cut off | Contaminated |
|---|---|---|---|---|---|---|---|---|---|
| bothuserhid | 7 | 7/7 | 7/7 | 9.6 | $0.169 | 20,510 | 0 | 0 | 0 |
| mainhid | 7 | 6/7 | 7/7 | 8.7 | $0.165 | 22,143 | 0 | 0 | 0 |
| nonehid | 7 | 5/7 | 7/7 | 9.1 | $0.148 | 18,009 | 0 | 0 | 0 |

## #418

| Arm | Runs | Acceptance | Suite | Turns | Cost per run | Context at first call | devkb queries | Cut off | Contaminated |
|---|---|---|---|---|---|---|---|---|---|
| bothuserhid | 7 | 7/7 | 7/7 | 20.0 | $0.416 | 21,494 | 1 | 0 | 0 |
| mainhid | 7 | 7/7 | 7/7 | 19.4 | $0.420 | 23,127 | 1 | 0 | 0 |
| nonehid | 7 | 7/7 | 7/7 | 21.6 | $0.440 | 19,008 | 0 | 0 | 0 |
