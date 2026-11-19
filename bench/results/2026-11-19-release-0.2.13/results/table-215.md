| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #215 | nonekeep | 3 | 3.4 (3.2–3.5) | 16.3 | 734 (566–852) | 11.0 | 0.35 (0.29–0.40) | 5.3 | 0.0 | 5.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 3.3 (3.1–3.5) | 16.0 | 767 (640–968) | 11.9 | 0.38 (0.33–0.45) | 5.0 | 0.0 | 3.3 | 0.0 | 2.0 (3679) | 3/3 | 3/3 | cost +7%, context +4% (within noise) |
|  | main | 3 | 3.9 (3.0–5.5) | 16.0 | 681 (540–779) | 10.0 | 0.33 (0.29–0.36) | 4.0 | 0.0 | 6.0 | 0.0 | 2.7 (4348) | 3/3 | 3/3 | cost -8%, context -7% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.35 | 734k | — | — |
| release | 3 | $0.38 | 767k | $+0.026 ($+0.026 to $+0.026) | +32k (+32k to +32k) |
| main | 3 | $0.33 | 681k | $-0.029 ($-0.029 to $-0.029) | -54k (-54k to -54k) |
