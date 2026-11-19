| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #217 | nonekeep | 3 | 5.4 (4.9–6.3) | 20.0 | 1043 (483–2112) | 8.3 | 0.36 (0.24–0.59) | 8.7 | 0.0 | 0.0 | 0.7 | 0.0 (0) | 0/3 | 3/3 |  |
|  | release | 3 | 5.2 (2.7–7.5) | 17.3 | 759 (386–1015) | 6.6 | 0.29 (0.22–0.35) | 4.3 | 0.0 | 0.0 | 0.3 | 2.3 (5344) | 0/3 | 3/3 | cost -19%, context -27% (within noise) |
|  | main | 3 | 3.9 (3.2–4.9) | 15.3 | 620 (512–718) | 6.5 | 0.26 (0.23–0.29) | 4.3 | 0.0 | 0.0 | 0.7 | 2.0 (1402) | 0/3 | 3/3 | cost -27%, context -41% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.36 | 1043k | — | — |
| release | 3 | $0.29 | 759k | $-0.069 ($-0.069 to $-0.069) | -283k (-283k to -283k) |
| main | 3 | $0.26 | 620k | $-0.096 ($-0.096 to $-0.096) | -423k (-423k to -423k) |
