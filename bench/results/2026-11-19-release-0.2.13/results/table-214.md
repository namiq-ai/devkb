| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #214 | nonekeep | 3 | 5.2 (4.8–5.5) | 26.0 | 1667 (1235–1919) | 27.4 | 0.73 (0.64–0.78) | 12.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 2/3 | 3/3 |  |
|  | release | 3 | 5.0 (4.7–5.3) | 21.7 | 1306 (1044–1623) | 26.0 | 0.66 (0.61–0.71) | 9.0 | 0.0 | 0.7 | 0.0 | 2.3 (3992) | 3/3 | 3/3 | cost -9%, context -22% (within noise) |
|  | main | 3 | 5.5 (4.3–7.3) | 23.0 | 1431 (1187–1893) | 25.5 | 0.67 (0.55–0.74) | 8.0 | 0.0 | 0.7 | 0.0 | 1.3 (2339) | 2/3 | 3/3 | cost -7%, context -14% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.73 | 1667k | — | — |
| release | 3 | $0.66 | 1306k | $-0.063 ($-0.063 to $-0.063) | -360k (-360k to -360k) |
| main | 3 | $0.67 | 1431k | $-0.052 ($-0.052 to $-0.052) | -235k (-235k to -235k) |
