| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #118 | nonekeep | 3 | 4.5 (3.8–6.0) | 27.0 | 1434 (1194–1751) | 13.7 | 0.49 (0.46–0.53) | 11.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 |  |
|  | release | 3 | 5.1 (3.4–6.1) | 21.0 | 1112 (876–1545) | 11.6 | 0.43 (0.39–0.50) | 9.3 | 0.0 | 0.0 | 0.0 | 2.0 (2717) | 3/3 | 3/3 | cost -12%, context -22% (within noise) |
|  | main | 3 | 7.8 (4.4–14.0) | 28.7 | 1698 (1478–1922) | 17.9 | 0.59 (0.48–0.66) | 11.3 | 0.0 | 0.0 | 0.0 | 1.0 (185) | 3/3 | 3/3 | cost +22%, context +18% (within noise) |
|  | teach | 3 | 4.7 (3.8–6.0) | 22.3 | 1153 (984–1411) | 12.9 | 0.46 (0.43–0.50) | 9.7 | 2.7 | 0.0 | 0.0 | 1.0 (137) | 3/3 | 3/3 | cost -6%, context -20% (within noise) |
|  | outline | 3 | 6.1 (3.7–8.5) | 29.3 | 1566 (1075–2471) | 14.4 | 0.51 (0.43–0.67) | 14.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 3/3 | 3/3 | cost +5%, context +9% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.49 | 1434k | — | — |
| release | 3 | $0.43 | 1112k | $-0.057 ($-0.057 to $-0.057) | -322k (-322k to -322k) |
| main | 3 | $0.59 | 1698k | $+0.107 ($+0.107 to $+0.107) | +264k (+264k to +264k) |
| teach | 3 | $0.46 | 1153k | $-0.027 ($-0.027 to $-0.027) | -281k (-281k to -281k) |
| outline | 3 | $0.51 | 1566k | $+0.024 ($+0.024 to $+0.024) | +133k (+133k to +133k) |
