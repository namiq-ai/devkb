| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #203 | nonekeep | 3 | 3.9 (3.2–5.2) | 20.7 | 845 (710–950) | 6.8 | 0.30 (0.26–0.32) | 7.0 | 0.3 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 3.8 (3.0–5.1) | 16.7 | 657 (607–723) | 6.9 | 0.27 (0.24–0.29) | 6.0 | 0.0 | 0.0 | 0.0 | 0.7 (567) | 3/3 | 3/3 | cost -11%, context -22% (within noise) |
|  | main | 3 | 6.6 (5.3–8.8) | 23.3 | 1002 (790–1142) | 9.0 | 0.34 (0.29–0.38) | 4.7 | 0.3 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost +14%, context +19% (within noise) |
|  | teach | 3 | 4.7 (3.1–5.7) | 17.3 | 668 (542–769) | 5.7 | 0.26 (0.22–0.28) | 6.7 | 2.0 | 0.0 | 0.0 | 0.3 (134) | 3/3 | 3/3 | cost -14%, context -21% (within noise) |
|  | outline | 3 | 10.4 (3.1–23.0) | 20.7 | 816 (715–1013) | 6.9 | 0.29 (0.28–0.31) | 8.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost -2%, context -3% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.30 | 845k | — | — |
| release | 3 | $0.27 | 657k | $-0.032 ($-0.032 to $-0.032) | -188k (-188k to -188k) |
| main | 3 | $0.34 | 1002k | $+0.043 ($+0.043 to $+0.043) | +157k (+157k to +157k) |
| teach | 3 | $0.26 | 668k | $-0.042 ($-0.042 to $-0.042) | -177k (-177k to -177k) |
| outline | 3 | $0.29 | 816k | $-0.006 ($-0.006 to $-0.006) | -29k (-29k to -29k) |
