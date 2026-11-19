| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #192 | nonekeep | 3 | 4.3 (2.7–5.3) | 16.0 | 589 (489–785) | 6.0 | 0.24 (0.21–0.29) | 6.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 1/3 | 3/3 |  |
|  | release | 3 | 3.8 (3.3–4.4) | 28.3 | 1232 (832–1643) | 12.2 | 0.41 (0.33–0.52) | 8.3 | 0.0 | 0.0 | 0.0 | 0.3 (343) | 3/3 | 3/3 | cost +70%, context +109% |
|  | main | 3 | 3.6 (2.8–4.9) | 16.3 | 590 (497–737) | 5.9 | 0.23 (0.21–0.27) | 4.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 2/3 | 3/3 | cost -3%, context +0% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.24 | 589k | — | — |
| release | 3 | $0.41 | 1232k | $+0.171 ($+0.171 to $+0.171) | +643k (+643k to +643k) |
| main | 3 | $0.23 | 590k | $-0.008 ($-0.008 to $-0.008) | +0k (+0k to +0k) |
