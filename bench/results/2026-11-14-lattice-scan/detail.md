Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| rca | L-ERR-_check_rows | 0.153 / 0.77 / 12 | 0.142 / 0.76 / 18 | 0.047 / 1.00 / 9 | 0.024 / 0.99 / 5 |
| rca | L-ERR-load | 0.125 / 0.71 / 11 | 0.085 / 0.86 / 11 | 0.085 / 0.88 / 11 | 0.028 / 0.94 / 5 |
| rca | L-ERR-terms_version | 0.154 / 0.70 / 14 | 0.121 / 0.71 / 18 | 0.150 / 0.71 / 20 | 0.144 / 0.70 / 13 |
| rca | L-ERR-verify_document | 0.177 / 0.77 / 17 | 0.131 / 0.86 / 16 | 0.033 / 0.96 / 5 | 0.016 / 1.00 / 3 |
| refactor | L-WIDE-candidate | 0.043 / 0.97 / 2 | 0.043 / 0.98 / 8 | 0.040 / 0.98 / 8 | 0.027 / 0.98 / 4 |
| refactor | L-WIDE-host_artefacts | 0.010 / 1.00 / 2 | 0.019 / 1.00 / 5 | 0.013 / 1.00 / 4 | 0.014 / 1.00 / 3 |
| refactor | L-WIDE-image_details | 0.013 / 1.00 / 2 | 0.017 / 1.00 / 5 | 0.013 / 1.00 / 4 | 0.010 / 1.00 / 2 |
| refactor | L-WIDE-impact | 0.027 / 1.00 / 3 | 0.029 / 1.00 / 6 | 0.013 / 1.00 / 3 | 0.011 / 1.00 / 2 |
| refactor | L-WIDE-inventory | 0.028 / 1.00 / 3 | 0.024 / 1.00 / 6 | 0.014 / 1.00 / 4 | 0.005 / 1.00 / 1 |
| refactor | L-WIDE-parse_rpm_sqlite | 0.010 / 1.00 / 2 | 0.018 / 1.00 / 5 | 0.012 / 1.00 / 4 | 0.005 / 1.00 / 1 |
| refactor | L-WIDE-posture_block | 0.009 / 1.00 / 2 | 0.020 / 1.00 / 5 | 0.014 / 1.00 / 4 | 0.010 / 1.00 / 2 |
| refactor | L-WIDE-preview | 0.016 / 1.00 / 3 | 0.018 / 1.00 / 5 | 0.012 / 1.00 / 3 | 0.013 / 1.00 / 2 |

Mean of each score part:

| rca | callers | raiser | tests | runs |
|---|---:|---:|---:|---:|
| plain | 0.69 | 1.00 | 0.51 | 20 |
| core | 0.75 | 1.00 | 0.65 | 20 |
| lean | 0.83 | 1.00 | 0.83 | 20 |
| pack | 0.83 | 1.00 | 0.89 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 1.00 | 40 |
| core | 0.99 | 1.00 | 40 |
| lean | 0.99 | 1.00 | 40 |
| pack | 0.99 | 1.00 | 40 |

Graph tools called (all runs):

- **plain**: $4.21 in all; none
- **core**: $3.66 in all; `callers` 131, `tests_for` 56, `graph_status` 7
- **lean**: $2.68 in all; `callers` 96, `tests_for` 55, `rca_trace` 20
- **pack**: $2.05 in all; none
