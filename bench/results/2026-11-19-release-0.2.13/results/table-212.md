| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #212 | nonekeep | 3 | 2.5 (2.5–2.6) | 12.3 | 380 (368–402) | 3.3 | 0.16 (0.15–0.17) | 4.0 | 0.0 | 0.3 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 3.4 (2.6–4.9) | 11.7 | 372 (274–488) | 4.1 | 0.17 (0.15–0.19) | 2.7 | 0.0 | 0.0 | 0.0 | 0.7 (587) | 3/3 | 3/3 | cost +7%, context -2% (within noise) |
|  | main | 3 | 3.1 (2.3–4.5) | 12.0 | 374 (234–526) | 3.0 | 0.15 (0.12–0.19) | 2.3 | 0.0 | 0.0 | 0.0 | 0.7 (315) | 3/3 | 3/3 | cost -4%, context -1% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.16 | 380k | — | — |
| release | 3 | $0.17 | 372k | $+0.011 ($+0.011 to $+0.011) | -8k (-8k to -8k) |
| main | 3 | $0.15 | 374k | $-0.007 ($-0.007 to $-0.007) | -6k (-6k to -6k) |
