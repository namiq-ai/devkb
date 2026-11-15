Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| refactor | devkb-WIDE-callers_of | 0.016 / 1.00 / 2 | 0.025 / 1.00 / 5 | 0.015 / 1.00 / 3 | 0.006 / 1.00 / 1 |
| refactor | devkb-WIDE-extract | 0.067 / 1.00 / 4 | 0.078 / 1.00 / 9 | 0.066 / 1.00 / 7 | 0.027 / 1.00 / 1 |
| refactor | devkb-WIDE-link_repository | 0.011 / 1.00 / 2 | 0.021 / 1.00 / 5 | 0.015 / 1.00 / 4 | 0.006 / 1.00 / 1 |
| refactor | devkb-WIDE-resolve | 0.048 / 0.97 / 3 | 0.060 / 0.99 / 7 | 0.056 / 0.99 / 7 | 0.037 / 0.99 / 5 |

Mean of each score part:

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 0.99 | 1.00 | 20 |
| core | 1.00 | 1.00 | 20 |
| lean | 0.99 | 1.00 | 20 |
| pack | 0.99 | 1.00 | 20 |

Graph tools called (all runs):

- **plain**: $0.92 in all; none
- **core**: $1.11 in all; `callers` 20, `tests_for` 12
- **lean**: $0.91 in all; `callers` 20, `tests_for` 11
- **pack**: $0.55 in all; none
