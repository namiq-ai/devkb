| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #196 | nonekeep | 3 | 3.4 (1.4–5.5) | 20.7 | 943 (847–1109) | 9.7 | 0.36 (0.32–0.39) | 7.0 | 0.0 | 0.7 | 0.0 | 0.0 (0) | 2/3 | 3/3 |  |
|  | release | 3 | 4.5 (3.1–5.3) | 12.3 | 530 (448–676) | 7.8 | 0.29 (0.25–0.32) | 3.3 | 0.0 | 0.7 | 0.0 | 1.0 (309) | 3/3 | 3/3 | cost -19%, context -44% |
|  | main | 3 | 3.9 (3.0–5.2) | 17.7 | 797 (695–881) | 8.9 | 0.34 (0.30–0.39) | 7.0 | 0.0 | 0.7 | 0.0 | 1.0 (696) | 2/3 | 3/3 | cost -5%, context -16% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.36 | 943k | — | — |
| release | 3 | $0.29 | 530k | $-0.069 ($-0.069 to $-0.069) | -413k (-413k to -413k) |
| main | 3 | $0.34 | 797k | $-0.018 ($-0.018 to $-0.018) | -146k (-146k to -146k) |
