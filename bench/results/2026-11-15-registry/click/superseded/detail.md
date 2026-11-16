Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| refactor | click-WIDE-_split_opt | 0.012 / 1.00 / 2 | 0.024 / 1.00 / 5 | 0.016 / 1.00 / 4 | 0.016 / 1.00 / 3 |
| refactor | click-WIDE-strip_ansi | 0.020 / 1.00 / 2 | 0.027 / 1.00 / 6 | 0.015 / 1.00 / 3 | 0.021 / 1.00 / 4 |
| refactor | click-WIDE-term_len | 0.014 / 1.00 / 2 | 0.023 / 1.00 / 5 | 0.016 / 1.00 / 4 | 0.020 / 1.00 / 3 |

Mean of each score part:

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 1.00 | 15 |
| core | 1.00 | 1.00 | 15 |
| lean | 1.00 | 1.00 | 15 |
| pack | 1.00 | 1.00 | 15 |

Graph tools called (all runs):

- **plain**: $0.35 in all; none
- **core**: $0.50 in all; `callers` 15, `tests_for` 15
- **lean**: $0.36 in all; `callers` 15, `tests_for` 10
- **pack**: $0.41 in all; none
