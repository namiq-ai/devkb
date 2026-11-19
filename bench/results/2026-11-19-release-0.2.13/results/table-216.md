| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #216 | nonekeep | 3 | 20.1 (19.4–21.4) | 55.3 | 5261 (3719–6372) | 50.7 | 1.51 (1.26–1.79) | 14.7 | 0.0 | 2.0 | 0.7 | 0.0 (0) | 0/3 | 3/3 |  |
|  | release | 3 | 15.8 (13.9–17.4) | 53.3 | 5485 (4675–6173) | 60.0 | 1.67 (1.53–1.77) | 16.0 | 0.0 | 3.7 | 1.7 | 2.0 (4495) | 0/3 | 3/3 | cost +11%, context +4% (within noise) |
|  | main | 3 | 17.9 (13.9–20.8) | 62.0 | 6802 (4543–7997) | 61.9 | 1.86 (1.42–2.13) | 19.3 | 0.0 | 3.0 | 3.0 | 2.3 (2453) | 1/3 | 3/3 | cost +23%, context +29% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $1.51 | 5261k | — | — |
| release | 3 | $1.67 | 5485k | $+0.162 ($+0.162 to $+0.162) | +224k (+224k to +224k) |
| main | 3 | $1.86 | 6802k | $+0.354 ($+0.354 to $+0.354) | +1541k (+1541k to +1541k) |
