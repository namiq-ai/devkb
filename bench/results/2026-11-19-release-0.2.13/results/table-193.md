| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #193 | nonekeep | 3 | 3.3 (0.8–5.9) | 17.0 | 581 (532–624) | 6.0 | 0.23 (0.21–0.24) | 5.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 2/3 |  |
|  | release | 3 | 11.9 (5.3–23.4) | 17.3 | 635 (596–681) | 6.2 | 0.25 (0.23–0.28) | 4.0 | 0.0 | 0.0 | 0.0 | 0.3 (281) | 3/3 | 3/3 | cost +12%, context +9% (within noise) |
|  | main | 3 | 3.4 (1.2–5.5) | 20.3 | 753 (588–875) | 6.8 | 0.27 (0.22–0.31) | 6.3 | 0.0 | 0.0 | 0.0 | 0.7 (704) | 3/3 | 2/3 | cost +17%, context +30% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.23 | 581k | — | — |
| release | 3 | $0.25 | 635k | $+0.026 ($+0.026 to $+0.026) | +54k (+54k to +54k) |
| main | 3 | $0.27 | 753k | $+0.039 ($+0.039 to $+0.039) | +172k (+172k to +172k) |
