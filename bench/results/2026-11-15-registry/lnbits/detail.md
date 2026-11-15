Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| err_to_handler | lnbits-ERR-decode_key | 0.143 / 0.90 / 16 | 0.124 / 0.94 / 13 | 0.035 / 1.00 / 5 | 0.006 / 1.00 / 1 |
| err_to_handler | lnbits-ERR-descriptor_script | 0.220 / 0.74 / 19 | 0.173 / 0.77 / 23 | 0.029 / 0.95 / 4 | 0.024 / 0.95 / 1 |
| err_to_handler | lnbits-ERR-onchain_key_status | 0.085 / 0.98 / 9 | 0.050 / 1.00 / 7 | 0.050 / 1.00 / 7 | 0.031 / 0.99 / 3 |
| err_to_handler | lnbits-ERR-validate_identity | 0.099 / 0.98 / 8 | 0.059 / 0.99 / 8 | 0.036 / 0.97 / 6 | 0.019 / 1.00 / 2 |
| impact | lnbits-IMP-clear_wallet_cache | 0.086 / 0.88 / 12 | 0.076 / 0.90 / 11 | 0.059 / 0.92 / 9 | 0.017 / 0.96 / 2 |
| impact | lnbits-IMP-create_access_token | 0.125 / 0.95 / 11 | 0.059 / 0.96 / 5 | 0.063 / 0.94 / 5 | 0.031 / 1.00 / 2 |
| impact | lnbits-IMP-scan_wallet | 0.070 / 1.00 / 10 | 0.066 / 1.00 / 13 | 0.046 / 1.00 / 9 | 0.020 / 1.00 / 3 |
| impact | lnbits-IMP-stop_wasm_extension_invocations | 0.117 / 0.86 / 12 | 0.059 / 0.86 / 5 | 0.027 / 0.88 / 3 | 0.021 / 1.00 / 3 |
| refactor | lnbits-WIDE-get_settings_field | 0.022 / 1.00 / 2 | 0.029 / 1.00 / 5 | 0.015 / 1.00 / 3 | 0.009 / 1.00 / 1 |
| refactor | lnbits-WIDE-get_wallet | 0.105 / 0.56 / 8 | 0.107 / 0.56 / 8 | 0.096 / 0.56 / 6 | 0.049 / 0.67 / 2 |
| refactor | lnbits-WIDE-random_secret_and_hash | 0.028 / 1.00 / 2 | 0.040 / 1.00 / 6 | 0.042 / 0.99 / 7 | 0.030 / 0.99 / 4 |
| refactor | lnbits-WIDE-set_settings_field | 0.026 / 1.00 / 2 | 0.034 / 1.00 / 5 | 0.032 / 1.00 / 5 | 0.028 / 0.97 / 3 |

Mean of each score part:

| err_to_handler | handlers | raiser | tests | runs |
|---|---:|---:|---:|---:|
| plain | 0.74 | 1.00 | 0.96 | 20 |
| core | 0.81 | 1.00 | 0.96 | 20 |
| lean | 0.98 | 1.00 | 0.96 | 20 |
| pack | 0.96 | 1.00 | 0.99 | 20 |

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 0.96 | 0.89 | 20 |
| core | 0.96 | 0.90 | 20 |
| lean | 0.97 | 0.89 | 20 |
| pack | 1.00 | 0.98 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 0.90 | 0.88 | 20 |
| core | 0.90 | 0.88 | 20 |
| lean | 0.90 | 0.88 | 20 |
| pack | 0.92 | 0.90 | 20 |

Graph tools called (all runs):

- **plain**: $5.99 in all; none
- **core**: $4.82 in all; `callers` 176, `tests_for` 31, `tests_to_run` 4, `graph_status` 1
- **lean**: $3.18 in all; `callers` 95, `tests_for` 23, `rca_trace` 20, `impact` 7, `tests_to_run` 6
- **pack**: $2.22 in all; none
