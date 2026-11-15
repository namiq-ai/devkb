Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| err_to_handler | prefect-ERR-from_page_token | 0.132 / 0.89 / 9 | 0.057 / 0.87 / 8 | 0.098 / 0.89 / 7 | 0.028 / 1.00 / 3 |
| impact | prefect-IMP-_automation_event | 0.213 / 1.00 / 14 | 0.162 / 1.00 / 15 | 0.108 / 0.98 / 12 | 0.052 / 0.99 / 6 |
| impact | prefect-IMP-_get_base_config_defaults | 0.192 / 0.80 / 13 | 0.125 / 0.97 / 11 | 0.089 / 0.90 / 10 | 0.036 / 0.95 / 4 |
| impact | prefect-IMP-_resolve_default_reference | 0.194 / 0.87 / 15 | 0.118 / 0.94 / 13 | 0.127 / 0.93 / 14 | 0.033 / 1.00 / 4 |
| impact | prefect-IMP-_sync_automation_related_resources | 0.162 / 0.98 / 13 | 0.089 / 0.99 / 9 | 0.026 / 0.76 / 3 | 0.079 / 1.00 / 4 |
| refactor | prefect-WIDE-Completed | 0.126 / 1.00 / 12 | 0.122 / 1.00 / 11 | 0.111 / 0.91 / 10 | 0.106 / 1.00 / 11 |
| refactor | prefect-WIDE-LimitBody | 0.038 / 1.00 / 2 | 0.038 / 1.00 / 5 | 0.031 / 1.00 / 5 | 0.023 / 1.00 / 2 |
| refactor | prefect-WIDE-command_to_string | 0.023 / 1.00 / 2 | 0.032 / 1.00 / 4 | 0.018 / 1.00 / 3 | 0.018 / 1.00 / 2 |
| refactor | prefect-WIDE-read_flow_run | 0.112 / 0.98 / 8 | 0.095 / 0.98 / 7 | 0.069 / 0.99 / 6 | 0.056 / 1.00 / 5 |

Mean of each score part:

| err_to_handler | handlers | raiser | tests | runs |
|---|---:|---:|---:|---:|
| plain | 1.00 | 1.00 | 0.67 | 5 |
| core | 0.67 | 1.00 | 0.93 | 5 |
| lean | 0.83 | 1.00 | 0.83 | 4 |
| pack | 1.00 | 1.00 | 1.00 | 5 |

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 0.97 | 0.86 | 20 |
| core | 0.97 | 0.98 | 20 |
| lean | 0.97 | 0.81 | 19 |
| pack | 0.99 | 0.98 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 0.99 | 20 |
| core | 1.00 | 0.99 | 20 |
| lean | 0.98 | 0.97 | 20 |
| pack | 1.00 | 1.00 | 20 |

Graph tools called (all runs):

- **plain**: $6.40 in all; none
- **core**: $4.64 in all; `callers` 110, `tests_for` 8, `tests_to_run` 4, `impact` 1
- **lean**: $3.56 in all; `callers` 71, `tests_for` 15, `impact` 12, `rca_trace` 4, `tests_to_run` 2
- **pack**: $2.63 in all; none
