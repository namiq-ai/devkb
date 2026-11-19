| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #194 | nonekeep | 3 | 4.9 (2.8–6.6) | 15.0 | 517 (440–594) | 6.3 | 0.23 (0.19–0.26) | 2.7 | 0.0 | 0.3 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 2.9 (2.7–3.3) | 10.0 | 322 (278–406) | 3.6 | 0.16 (0.14–0.19) | 2.0 | 0.0 | 0.7 | 0.0 | 0.7 (34) | 3/3 | 3/3 | cost -28%, context -38% |
|  | main | 3 | 3.8 (3.0–4.5) | 13.0 | 435 (326–619) | 4.6 | 0.19 (0.16–0.24) | 3.7 | 0.0 | 0.0 | 0.0 | 0.3 (320) | 3/3 | 3/3 | cost -17%, context -16% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.23 | 517k | — | — |
| release | 3 | $0.16 | 322k | $-0.064 ($-0.064 to $-0.064) | -195k (-195k to -195k) |
| main | 3 | $0.19 | 435k | $-0.038 ($-0.038 to $-0.038) | -82k (-82k to -82k) |
