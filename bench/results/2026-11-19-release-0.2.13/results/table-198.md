| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #198 | nonekeep | 3 | 3.8 (1.2–6.3) | 22.3 | 898 (722–1070) | 10.1 | 0.33 (0.30–0.36) | 6.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 1/3 | 1/3 |  |
|  | release | 3 | 11.2 (5.2–22.7) | 15.3 | 597 (558–652) | 7.9 | 0.27 (0.26–0.29) | 3.3 | 0.0 | 0.0 | 0.0 | 1.0 (835) | 1/3 | 3/3 | cost -18%, context -34% |
|  | main | 3 | 11.8 (4.9–24.9) | 16.3 | 655 (552–738) | 8.1 | 0.28 (0.25–0.32) | 4.0 | 0.0 | 0.3 | 0.0 | 1.0 (575) | 2/3 | 3/3 | cost -14%, context -27% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.33 | 898k | — | — |
| release | 3 | $0.27 | 597k | $-0.058 ($-0.058 to $-0.058) | -301k (-301k to -301k) |
| main | 3 | $0.28 | 655k | $-0.047 ($-0.047 to $-0.047) | -242k (-242k to -242k) |
