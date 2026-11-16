Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| refactor | click-WIDE-confirm | 0.023 / 0.88 / 3 | 0.020 / 1.00 / 4 | 0.016 / 1.00 / 4 | 0.014 / 1.00 / 2 |
| refactor | click-WIDE-echo_via_pager | 0.018 / 0.96 / 2 | 0.022 / 1.00 / 5 | 0.014 / 1.00 / 4 | 0.012 / 1.00 / 2 |
| refactor | click-WIDE-help_option | 0.025 / 1.00 / 2 | 0.032 / 1.00 / 6 | 0.020 / 1.00 / 3 | 0.021 / 1.00 / 3 |
| refactor | click-WIDE-make_pass_decorator | 0.018 / 0.98 / 3 | 0.024 / 1.00 / 5 | 0.015 / 1.00 / 3 | 0.012 / 1.00 / 2 |
| refactor | click-WIDE-option | 0.040 / 1.00 / 4 | 0.044 / 1.00 / 6 | 0.055 / 1.00 / 6 | 0.027 / 1.00 / 3 |
| refactor | click-WIDE-prompt | 0.027 / 1.00 / 4 | 0.026 / 1.00 / 5 | 0.017 / 0.95 / 4 | 0.014 / 1.00 / 2 |
| refactor | click-WIDE-strip_ansi | 0.019 / 1.00 / 2 | 0.027 / 1.00 / 7 | 0.013 / 1.00 / 3 | 0.021 / 1.00 / 4 |
| refactor | click-WIDE-term_len | 0.014 / 1.00 / 2 | 0.024 / 1.00 / 5 | 0.016 / 1.00 / 4 | 0.019 / 1.00 / 3 |

Mean of each score part:

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 0.97 | 0.99 | 40 |
| core | 1.00 | 1.00 | 40 |
| lean | 1.00 | 0.99 | 40 |
| pack | 1.00 | 1.00 | 40 |

Graph tools called (all runs):

- **plain**: $1.30 in all; none
- **core**: $1.51 in all; `callers` 40, `tests_for` 34
- **lean**: $1.22 in all; `callers` 40, `tests_for` 21
- **pack**: $1.11 in all; none
