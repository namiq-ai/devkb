| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #182 | nonekeep | 3 | 5.5 (4.9–6.0) | 20.7 | 798 (653–940) | 7.1 | 0.28 (0.27–0.30) | 6.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 5.7 (5.5–5.8) | 17.7 | 716 (550–987) | 7.4 | 0.29 (0.25–0.35) | 5.0 | 0.0 | 0.0 | 0.0 | 2.0 (3437) | 3/3 | 3/3 | cost +1%, context -10% (within noise) |
|  | main | 3 | 4.3 (3.7–4.8) | 15.0 | 571 (469–675) | 6.9 | 0.26 (0.23–0.27) | 6.7 | 0.0 | 0.0 | 0.0 | 1.0 (474) | 3/3 | 3/3 | cost -9%, context -28% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.28 | 798k | — | — |
| release | 3 | $0.29 | 716k | $+0.002 ($+0.002 to $+0.002) | -82k (-82k to -82k) |
| main | 3 | $0.26 | 571k | $-0.026 ($-0.026 to $-0.026) | -226k (-226k to -226k) |
