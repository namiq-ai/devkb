Per task: median cost $ / mean score / median turns.

| kind | task | plain | lean | lean-pack | pack |
|---|---|---|---|---|---|
| err_to_handler | lnbits-ERR-check_users_limit | 0.135 / 0.99 / 14 | 0.070 / 0.86 / 5 | 0.036 / 1.00 / 5 | 0.034 / 1.00 / 5 |
| err_to_handler | lnbits-ERR-decode_key | 0.143 / 0.91 / 13 | 0.033 / 1.00 / 5 | 0.014 / 1.00 / 3 | 0.007 / 1.00 / 1 |
| err_to_handler | lnbits-ERR-onchain_key_status | 0.089 / 0.98 / 9 | 0.045 / 1.00 / 6 | 0.044 / 0.99 / 5 | 0.036 / 0.99 / 4 |
| err_to_handler | lnbits-ERR-validate_identity | 0.096 / 0.98 / 8 | 0.033 / 0.97 / 6 | 0.016 / 1.00 / 3 | 0.020 / 0.99 / 3 |
| impact | lnbits-IMP-explorer_client | 0.109 / 1.00 / 9 | 0.049 / 1.00 / 7 | 0.014 / 1.00 / 3 | 0.009 / 1.00 / 1 |
| impact | lnbits-IMP-generate_filter_params_openapi | 0.078 / 0.70 / 10 | 0.042 / 1.00 / 6 | 0.016 / 1.00 / 3 | 0.026 / 1.00 / 3 |
| impact | lnbits-IMP-get_wallet_addresses | 0.127 / 1.00 / 15 | 0.051 / 1.00 / 10 | 0.015 / 1.00 / 3 | 0.022 / 1.00 / 3 |
| impact | lnbits-IMP-is_wasm_extension_id | 0.149 / 1.00 / 14 | 0.068 / 0.99 / 8 | 0.015 / 1.00 / 3 | 0.016 / 1.00 / 2 |
| refactor | lnbits-WIDE-create_account | 0.017 / 1.00 / 2 | 0.016 / 1.00 / 3 | 0.031 / 1.00 / 5 | 0.017 / 1.00 / 2 |
| refactor | lnbits-WIDE-get_wallets | 0.020 / 1.00 / 2 | 0.015 / 1.00 / 3 | 0.021 / 1.00 / 4 | 0.022 / 1.00 / 3 |
| refactor | lnbits-WIDE-pay_offer | 0.044 / 1.00 / 2 | 0.060 / 1.00 / 6 | 0.068 / 1.00 / 8 | 0.034 / 1.00 / 3 |
| refactor | lnbits-WIDE-update_wallet_balance | 0.027 / 0.99 / 2 | 0.044 / 1.00 / 5 | 0.022 / 1.00 / 3 | 0.021 / 1.00 / 2 |

Mean of each score part:

| err_to_handler | handlers | raiser | tests | runs |
|---|---:|---:|---:|---:|
| plain | 0.90 | 1.00 | 1.00 | 20 |
| lean | 0.98 | 1.00 | 0.90 | 20 |
| lean-pack | 0.99 | 1.00 | 1.00 | 20 |
| pack | 0.99 | 1.00 | 1.00 | 20 |

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 0.85 | 20 |
| lean | 1.00 | 1.00 | 20 |
| lean-pack | 1.00 | 1.00 | 20 |
| pack | 1.00 | 1.00 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 1.00 | 20 |
| lean | 1.00 | 1.00 | 20 |
| lean-pack | 1.00 | 1.00 | 20 |
| pack | 1.00 | 1.00 | 20 |

Graph tools called (all runs):

- **plain**: $5.75 in all; none
- **lean**: $3.15 in all; `callers` 129, `tests_for` 26, `rca_trace` 20, `tests_to_run` 8, `impact` 5
- **lean-pack**: $2.47 in all; `pack` 60, `callers` 18
- **pack**: $2.01 in all; none
