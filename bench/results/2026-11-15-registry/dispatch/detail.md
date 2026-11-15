Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| err_to_handler | dispatch-ERR-update | 0.061 / 1.00 / 8 | 0.055 / 1.00 / 10 | 0.038 / 1.00 / 7 | 0.019 / 1.00 / 3 |
| impact | dispatch-IMP-get_by_name_or_raise | 0.104 / 1.00 / 12 | 0.070 / 0.97 / 8 | 0.027 / 1.00 / 4 | 0.075 / 1.00 / 9 |
| impact | dispatch-IMP-get_signal_engagement_by_name | 0.120 / 1.00 / 12 | 0.065 / 1.00 / 11 | 0.038 / 1.00 / 7 | 0.032 / 1.00 / 4 |
| impact | dispatch-IMP-get_signal_filter_by_name | 0.110 / 1.00 / 13 | 0.061 / 1.00 / 12 | 0.046 / 1.00 / 9 | 0.033 / 1.00 / 4 |
| impact | dispatch-IMP-update_group | 0.314 / 0.50 / 27 | 0.165 / 0.59 / 20 | 0.134 / 0.74 / 20 | 0.007 / 1.00 / 1 |
| refactor | dispatch-WIDE-get_by_email_and_project | 0.016 / 1.00 / 2 | 0.025 / 1.00 / 4 | 0.016 / 1.00 / 3 | 0.015 / 1.00 / 2 |
| refactor | dispatch-WIDE-log_case_event | 0.026 / 0.97 / 2 | 0.041 / 0.98 / 6 | 0.042 / 1.00 / 6 | 0.031 / 1.00 / 3 |
| refactor | dispatch-WIDE-log_incident_event | 0.034 / 0.85 / 4 | 0.040 / 0.90 / 6 | 0.050 / 0.89 / 7 | 0.029 / 0.96 / 3 |

Mean of each score part:

| err_to_handler | handlers | raiser | tests | runs |
|---|---:|---:|---:|---:|
| plain | 1.00 | 1.00 | 1.00 | 5 |
| core | 1.00 | 1.00 | 1.00 | 5 |
| lean | 1.00 | 1.00 | 1.00 | 5 |
| pack | 1.00 | 1.00 | 1.00 | 5 |

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 0.82 | 0.93 | 20 |
| core | 0.83 | 0.95 | 20 |
| lean | 0.87 | 1.00 | 20 |
| pack | 1.00 | 1.00 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 0.99 | 0.89 | 15 |
| core | 0.99 | 0.92 | 15 |
| lean | 0.99 | 0.93 | 15 |
| pack | 1.00 | 0.98 | 15 |

Graph tools called (all runs):

- **plain**: $4.16 in all; none
- **core**: $3.06 in all; `callers` 106, `tests_for` 8, `tests_to_run` 6, `impact` 5
- **lean**: $2.29 in all; `callers` 84, `tests_for` 19, `impact` 7, `tests_to_run` 5, `rca_trace` 5
- **pack**: $1.63 in all; none
