Per task: median cost $ / mean score / median turns.

| kind | task | plain | lean | lean-pack | pack |
|---|---|---|---|---|---|
| err_to_handler | dispatch-ERR-update | 0.052 / 1.00 / 9 | 0.040 / 1.00 / 7 | 0.023 / 1.00 / 5 | 0.017 / 1.00 / 2 |
| impact | dispatch-IMP-get_by_name_or_raise | 0.113 / 1.00 / 13 | 0.055 / 1.00 / 11 | 0.072 / 1.00 / 10 | 0.063 / 1.00 / 6 |
| impact | dispatch-IMP-get_signal_engagement_by_name | 0.106 / 1.00 / 15 | 0.039 / 1.00 / 7 | 0.041 / 1.00 / 5 | 0.034 / 1.00 / 4 |
| impact | dispatch-IMP-get_signal_filter_by_name | 0.106 / 1.00 / 13 | 0.052 / 1.00 / 9 | 0.041 / 0.97 / 6 | 0.040 / 1.00 / 4 |
| impact | dispatch-IMP-update_group | 0.251 / 0.39 / 25 | 0.126 / 0.74 / 18 | 0.013 / 1.00 / 3 | 0.075 / 0.72 / 9 |
| refactor | dispatch-WIDE-get_by_email_and_project | 0.016 / 1.00 / 2 | 0.017 / 1.00 / 3 | 0.017 / 1.00 / 4 | 0.021 / 1.00 / 3 |
| refactor | dispatch-WIDE-log_case_event | 0.025 / 0.98 / 2 | 0.044 / 1.00 / 6 | 0.059 / 1.00 / 9 | 0.030 / 1.00 / 3 |
| refactor | dispatch-WIDE-log_incident_event | 0.026 / 0.82 / 3 | 0.044 / 0.93 / 6 | 0.056 / 0.93 / 7 | 0.031 / 0.89 / 3 |

Mean of each score part:

| err_to_handler | handlers | raiser | tests | runs |
|---|---:|---:|---:|---:|
| plain | 1.00 | 1.00 | 1.00 | 5 |
| lean | 1.00 | 1.00 | 1.00 | 5 |
| lean-pack | 1.00 | 1.00 | 1.00 | 5 |
| pack | 1.00 | 1.00 | 1.00 | 5 |

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 0.81 | 0.88 | 20 |
| lean | 0.88 | 0.98 | 20 |
| lean-pack | 1.00 | 0.98 | 20 |
| pack | 0.86 | 1.00 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 0.99 | 0.88 | 15 |
| lean | 1.00 | 0.96 | 15 |
| lean-pack | 1.00 | 0.96 | 15 |
| pack | 0.99 | 0.93 | 15 |

Graph tools called (all runs):

- **plain**: $3.80 in all; none
- **lean**: $2.43 in all; `callers` 111, `tests_for` 16, `tests_to_run` 7, `rca_trace` 5, `impact` 5
- **lean-pack**: $2.04 in all; `pack` 44, `callers` 18, `tests_for` 2
- **pack**: $2.03 in all; none
