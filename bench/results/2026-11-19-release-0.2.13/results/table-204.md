| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #204 | nonekeep | 3 | 2.4 (2.3–2.5) | 10.0 | 311 (239–439) | 2.2 | 0.14 (0.12–0.17) | 2.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 2.6 (2.5–2.8) | 16.0 | 551 (335–660) | 3.7 | 0.20 (0.15–0.24) | 3.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost +45%, context +77% (within noise) |
|  | main | 3 | 2.7 (2.5–2.8) | 13.7 | 450 (272–639) | 2.7 | 0.17 (0.13–0.22) | 3.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost +23%, context +45% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.14 | 311k | — | — |
| release | 3 | $0.20 | 551k | $+0.062 ($+0.062 to $+0.062) | +240k (+240k to +240k) |
| main | 3 | $0.17 | 450k | $+0.032 ($+0.032 to $+0.032) | +140k (+140k to +140k) |
