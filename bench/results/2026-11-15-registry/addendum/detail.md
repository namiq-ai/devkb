Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| impact | lnbits-IMP-clear_wallet_cache | 0.086 / 0.97 / 14 | 0.050 / 0.98 / 8 | 0.059 / 0.99 / 7 | 0.006 / 1.00 / 1 |
| refactor | lnbits-WIDE-get_wallet | 0.091 / 1.00 / 8 | 0.097 / 1.00 / 8 | 0.105 / 1.00 / 9 | 0.036 / 1.00 / 3 |
| refactor | mealie-WIDE-get_app_dirs | 0.024 / 1.00 / 3 | 0.026 / 1.00 / 4 | 0.016 / 1.00 / 3 | 0.016 / 1.00 / 2 |

Mean of each score part:

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 0.95 | 5 |
| core | 1.00 | 0.95 | 5 |
| lean | 1.00 | 0.98 | 5 |
| pack | 1.00 | 1.00 | 5 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 1.00 | 10 |
| core | 1.00 | 1.00 | 10 |
| lean | 1.00 | 1.00 | 10 |
| pack | 1.00 | 1.00 | 10 |

Graph tools called (all runs):

- **plain**: $1.03 in all; none
- **core**: $0.96 in all; `callers` 36, `tests_for` 1
- **lean**: $0.96 in all; `callers` 33, `tests_for` 12, `impact` 2, `tests_to_run` 1
- **pack**: $0.30 in all; none
