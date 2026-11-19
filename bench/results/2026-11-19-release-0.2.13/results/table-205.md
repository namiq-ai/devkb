| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #205 | nonekeep | 3 | 7.2 (3.8–9.2) | 24.7 | 1378 (1183–1677) | 15.9 | 0.52 (0.50–0.53) | 6.3 | 0.3 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 6.6 (5.6–8.4) | 24.7 | 1479 (847–2325) | 14.3 | 0.52 (0.45–0.65) | 6.3 | 0.0 | 0.0 | 0.0 | 1.3 (1393) | 3/3 | 2/3 | cost +1%, context +7% (within noise) |
|  | main | 3 | 6.8 (5.5–9.0) | 20.7 | 1113 (979–1267) | 12.9 | 0.44 (0.36–0.49) | 6.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost -14%, context -19% |
|  | outline | 3 | 6.2 (3.8–8.2) | 24.0 | 1474 (781–2293) | 16.7 | 0.57 (0.42–0.70) | 6.7 | 0.3 | 0.0 | 0.0 | 0.7 (1016) | 3/3 | 2/3 | cost +9%, context +7% (within noise) |
|  | teach | 3 | 7.5 (3.8–12.6) | 24.0 | 1392 (881–2002) | 14.6 | 0.50 (0.43–0.58) | 6.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost -3%, context +1% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.52 | 1378k | — | — |
| release | 3 | $0.52 | 1479k | $+0.004 ($+0.004 to $+0.004) | +101k (+101k to +101k) |
| main | 3 | $0.44 | 1113k | $-0.074 ($-0.074 to $-0.074) | -265k (-265k to -265k) |
| outline | 3 | $0.57 | 1474k | $+0.048 ($+0.048 to $+0.048) | +96k (+96k to +96k) |
| teach | 3 | $0.50 | 1392k | $-0.013 ($-0.013 to $-0.013) | +14k (+14k to +14k) |
