| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #175 | nonekeep | 3 | 2.5 (0.7–3.5) | 16.7 | 679 (369–1048) | 6.6 | 0.28 (0.22–0.34) | 6.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 2/3 |  |
|  | release | 3 | 5.2 (3.4–7.5) | 15.7 | 672 (561–854) | 7.6 | 0.29 (0.27–0.31) | 4.3 | 0.0 | 0.0 | 0.0 | 2.7 (2563) | 3/3 | 3/3 | cost +5%, context -1% (within noise) |
|  | main | 3 | 3.9 (3.0–5.4) | 13.0 | 510 (417–684) | 6.2 | 0.25 (0.22–0.27) | 5.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost -12%, context -25% (within noise) |
|  | outline | 3 | 2.6 (0.7–3.8) | 14.3 | 574 (377–907) | 5.9 | 0.26 (0.22–0.31) | 8.0 | 0.0 | 0.0 | 0.3 | 2.3 (2155) | 3/3 | 2/3 | cost -6%, context -15% (within noise) |
|  | teach | 3 | 3.8 (3.0–5.2) | 18.0 | 799 (377–1017) | 6.6 | 0.30 (0.21–0.36) | 6.0 | 1.0 | 0.0 | 0.0 | 1.0 (488) | 3/3 | 3/3 | cost +9%, context +18% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.28 | 679k | — | — |
| release | 3 | $0.29 | 672k | $+0.013 ($+0.013 to $+0.013) | -7k (-7k to -7k) |
| main | 3 | $0.25 | 510k | $-0.033 ($-0.033 to $-0.033) | -169k (-169k to -169k) |
| outline | 3 | $0.26 | 574k | $-0.017 ($-0.017 to $-0.017) | -104k (-104k to -104k) |
| teach | 3 | $0.30 | 799k | $+0.025 ($+0.025 to $+0.025) | +121k (+121k to +121k) |
