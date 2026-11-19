| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #137 | nonekeep | 3 | 4.8 (3.7–6.9) | 21.7 | 1025 (799–1377) | 9.4 | 0.37 (0.33–0.43) | 7.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0/3 | 3/3 |  |
|  | release | 3 | 4.4 (3.7–5.7) | 24.7 | 1231 (1152–1307) | 9.4 | 0.40 (0.39–0.42) | 8.0 | 1.7 | 0.0 | 0.0 | 1.7 (1890) | 0/3 | 3/3 | cost +8%, context +20% (within noise) |
|  | main | 3 | 5.2 (4.0–6.0) | 21.7 | 1080 (899–1262) | 9.9 | 0.40 (0.33–0.44) | 8.3 | 0.3 | 0.0 | 0.3 | 0.7 (1015) | 0/3 | 3/3 | cost +6%, context +5% (within noise) |
|  | teach | 3 | 4.1 (3.2–5.5) | 17.3 | 789 (610–890) | 7.0 | 0.31 (0.29–0.33) | 7.3 | 1.0 | 0.0 | 0.0 | 1.0 (1164) | 0/3 | 3/3 | cost -16%, context -23% (within noise) |
|  | outline | 3 | 4.8 (3.7–5.8) | 18.7 | 1034 (661–1738) | 7.2 | 0.37 (0.29–0.53) | 7.3 | 1.0 | 0.0 | 0.3 | 1.3 (1357) | 0/3 | 3/3 | cost -0%, context +1% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.37 | 1025k | — | — |
| release | 3 | $0.40 | 1231k | $+0.028 ($+0.028 to $+0.028) | +206k (+206k to +206k) |
| main | 3 | $0.40 | 1080k | $+0.023 ($+0.023 to $+0.023) | +55k (+55k to +55k) |
| teach | 3 | $0.31 | 789k | $-0.059 ($-0.059 to $-0.059) | -236k (-236k to -236k) |
| outline | 3 | $0.37 | 1034k | $-0.001 ($-0.001 to $-0.001) | +9k (+9k to +9k) |
