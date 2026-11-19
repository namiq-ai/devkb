| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #195 | nonekeep | 3 | 2.1 (0.9–2.7) | 11.3 | 361 (276–512) | 4.2 | 0.17 (0.14–0.23) | 4.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 2.5 (2.4–2.7) | 9.3 | 293 (211–401) | 3.0 | 0.15 (0.12–0.17) | 3.3 | 0.0 | 0.0 | 0.0 | 1.0 (2341) | 3/3 | 3/3 | cost -14%, context -19% (within noise) |
|  | main | 3 | 2.6 (2.5–2.6) | 9.7 | 299 (275–336) | 3.4 | 0.15 (0.14–0.16) | 2.7 | 0.0 | 0.0 | 0.0 | 0.7 (750) | 3/3 | 3/3 | cost -11%, context -17% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.17 | 361k | — | — |
| release | 3 | $0.15 | 293k | $-0.024 ($-0.024 to $-0.024) | -67k (-67k to -67k) |
| main | 3 | $0.15 | 299k | $-0.019 ($-0.019 to $-0.019) | -62k (-62k to -62k) |
