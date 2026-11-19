| Ticket | Arm | Runs | Wall min | Turns | Context k | Output k | Cost $ | Grep | devkb nav | devkb self-tests | Replaced | Hook answers (chars) | Hidden check | Suite | vs no devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #120 | nonekeep | 3 | 5.7 (4.6–6.7) | 25.7 | 1558 (650–2300) | 25.1 | 0.69 (0.52–0.85) | 9.7 | 1.0 | 0.0 | 0.0 | 0.0 (0) | 2/3 | 3/3 |  |
|  | release | 3 | 7.9 (7.1–9.0) | 28.3 | 2162 (1549–2883) | 30.2 | 0.85 (0.72–1.09) | 9.7 | 0.0 | 0.0 | 0.0 | 2.3 (5657) | 3/3 | 3/3 | cost +24%, context +39% (within noise) |
|  | main | 3 | 6.3 (4.0–8.0) | 32.3 | 2390 (1138–3579) | 26.2 | 0.81 (0.51–1.09) | 11.7 | 0.3 | 0.0 | 0.0 | 2.0 (1011) | 2/3 | 3/3 | cost +18%, context +53% (within noise) |
|  | teach | 3 | 6.4 (4.4–9.9) | 23.7 | 1385 (1169–1813) | 22.2 | 0.61 (0.53–0.72) | 10.0 | 2.3 | 0.0 | 0.0 | 1.3 (1555) | 3/3 | 3/3 | cost -10%, context -11% (within noise) |
|  | outline | 3 | 7.2 (6.6–7.7) | 32.0 | 2262 (1811–2549) | 29.0 | 0.84 (0.78–0.89) | 10.0 | 1.3 | 0.0 | 0.0 | 3.3 (1691) | 2/3 | 3/3 | cost +22%, context +45% (within noise) |

| Release, arm | Runs | Cost per run | Context per run | Cost difference vs no devkb (90% interval) | Context difference (90% interval) |
|---|---|---|---|---|---|
| nonekeep | 3 | $0.69 | 1558k | — | — |
| release | 3 | $0.85 | 2162k | $+0.164 ($+0.164 to $+0.164) | +604k (+604k to +604k) |
| main | 3 | $0.81 | 2390k | $+0.126 ($+0.126 to $+0.126) | +832k (+832k to +832k) |
| teach | 3 | $0.61 | 1385k | $-0.071 ($-0.071 to $-0.071) | -173k (-173k to -173k) |
| outline | 3 | $0.84 | 2262k | $+0.150 ($+0.150 to $+0.150) | +705k (+705k to +705k) |
