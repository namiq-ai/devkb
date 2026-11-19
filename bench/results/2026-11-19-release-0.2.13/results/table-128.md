| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #128 | nonekeep | 3 | 3.5 (2.6–4.9) | 13.3 | 427 (309–497) | 3.8 | 0.17 (0.15–0.20) | 5.0 | 0.0 | 0.3 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 10.9 (4.9–22.2) | 15.3 | 533 (391–770) | 5.3 | 0.21 (0.17–0.29) | 5.0 | 0.0 | 0.0 | 0.0 | 1.3 (870) | 3/3 | 3/3 | cost +23%, context +25% (within noise) |
|  | main | 3 | 3.3 (2.5–4.7) | 13.7 | 462 (388–526) | 3.7 | 0.19 (0.16–0.21) | 3.7 | 0.0 | 0.0 | 0.0 | 1.7 (357) | 3/3 | 3/3 | cost +7%, context +8% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.17 | 427k | — | — |
| release | 3 | $0.21 | 533k | $+0.040 ($+0.040 to $+0.040) | +106k (+106k to +106k) |
| main | 3 | $0.19 | 462k | $+0.012 ($+0.012 to $+0.012) | +35k (+35k to +35k) |
