| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #187 | nonekeep | 3 | 3.7 (0.9–5.2) | 17.7 | 701 (526–967) | 7.9 | 0.28 (0.24–0.35) | 8.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 2/3 |  |
|  | release | 3 | 6.8 (5.7–8.8) | 18.0 | 758 (524–918) | 7.7 | 0.30 (0.27–0.34) | 6.0 | 0.0 | 0.0 | 0.0 | 1.7 (1929) | 3/3 | 1/3 | cost +7%, context +8% (within noise) |
|  | main | 3 | 5.0 (0.9–8.6) | 17.0 | 682 (624–795) | 7.9 | 0.29 (0.26–0.33) | 5.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 2/3 | cost +1%, context -3% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.28 | 701k | — | — |
| release | 3 | $0.30 | 758k | $+0.018 ($+0.018 to $+0.018) | +58k (+58k to +58k) |
| main | 3 | $0.29 | 682k | $+0.003 ($+0.003 to $+0.003) | -18k (-18k to -18k) |
