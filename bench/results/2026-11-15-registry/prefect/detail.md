Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| err_to_handler | prefect-ERR-from_page_token | 0.150 / 0.82 / 10 | 0.138 / 0.89 / 8 | 0.136 / 0.83 / 7 | 0.026 / 1.00 / 2 |
| impact | prefect-IMP-_automation_event | 0.194 / 1.00 / 13 | 0.203 / 1.00 / 14 | 0.187 / 0.99 / 10 | 0.021 / 1.00 / 2 |
| impact | prefect-IMP-_get_base_config_defaults | 0.188 / 0.83 / 14 | 0.241 / 0.86 / 18 | 0.208 / 0.82 / 14 | 0.047 / 1.00 / 4 |
| impact | prefect-IMP-_resolve_default_reference | 0.208 / 0.93 / 15 | 0.198 / 0.87 / 16 | 0.239 / 0.87 / 16 | 0.049 / 0.89 / 5 |
| impact | prefect-IMP-_sync_automation_related_resources | 0.165 / 0.98 / 10 | 0.169 / 1.00 / 10 | 0.101 / 1.00 / 9 | 0.021 / 1.00 / 2 |
| refactor | prefect-WIDE-Completed | 0.150 / 1.00 / 15 | 0.125 / 1.00 / 9 | 0.098 / 1.00 / 9 | 0.083 / 1.00 / 7 |
| refactor | prefect-WIDE-LimitBody | 0.044 / 1.00 / 3 | 0.034 / 1.00 / 3 | 0.022 / 1.00 / 2 | 0.022 / 1.00 / 2 |
| refactor | prefect-WIDE-command_to_string | 0.024 / 1.00 / 2 | 0.023 / 1.00 / 2 | 0.027 / 1.00 / 3 | 0.018 / 1.00 / 2 |
| refactor | prefect-WIDE-read_flow_run | 0.079 / 0.64 / 6 | 0.121 / 0.65 / 6 | 0.088 / 0.65 / 8 | 0.092 / 0.74 / 7 |

Mean of each score part:

| err_to_handler | handlers | raiser | tests | runs |
|---|---:|---:|---:|---:|
| plain | 0.73 | 1.00 | 0.73 | 5 |
| core | 0.87 | 1.00 | 0.80 | 5 |
| lean | 0.87 | 1.00 | 0.63 | 5 |
| pack | 1.00 | 1.00 | 1.00 | 5 |

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 0.96 | 0.91 | 20 |
| core | 0.97 | 0.90 | 20 |
| lean | 0.96 | 0.88 | 20 |
| pack | 0.99 | 0.95 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 0.91 | 0.91 | 20 |
| core | 0.91 | 0.92 | 20 |
| lean | 0.91 | 0.92 | 20 |
| pack | 0.94 | 0.93 | 20 |

Graph tools called (all runs):

- **plain**: $6.25 in all; none
- **core**: $6.54 in all; none
- **lean**: $6.06 in all; none
- **pack**: $2.41 in all; none
