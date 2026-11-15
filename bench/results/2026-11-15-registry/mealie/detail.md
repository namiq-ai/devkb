Per task: median cost $ / mean score / median turns.

| kind | task | plain | core | lean | pack |
|---|---|---|---|---|---|
| impact | mealie-IMP-publish_list_item_events | 0.087 / 0.67 / 9 | 0.068 / 0.88 / 6 | 0.042 / 1.00 / 5 | 0.043 / 0.87 / 2 |
| impact | mealie-IMP-request_is_https | 0.083 / 0.74 / 9 | 0.046 / 1.00 / 8 | 0.041 / 1.00 / 6 | 0.006 / 1.00 / 1 |
| impact | mealie-IMP-session_cookie_attrs | 0.061 / 1.00 / 8 | 0.070 / 1.00 / 7 | 0.064 / 1.00 / 9 | 0.037 / 0.93 / 5 |
| impact | mealie-IMP-set_session_cookie | 0.033 / 0.94 / 4 | 0.065 / 0.93 / 8 | 0.040 / 0.94 / 6 | 0.018 / 0.88 / 2 |
| refactor | mealie-WIDE-get_app_dirs | 0.024 / 0.94 / 2 | 0.036 / 0.94 / 5 | 0.017 / 1.00 / 3 | 0.027 / 0.94 / 3 |
| refactor | mealie-WIDE-get_locale_provider | 0.041 / 0.77 / 2 | 0.067 / 0.76 / 5 | 0.061 / 0.76 / 5 | 0.044 / 0.81 / 3 |
| refactor | mealie-WIDE-session_context | 0.044 / 1.00 / 2 | 0.045 / 1.00 / 6 | 0.045 / 0.99 / 6 | 0.024 / 1.00 / 2 |

Mean of each score part:

| impact | handlers | tests | runs |
|---|---:|---:|---:|
| plain | 1.00 | 0.67 | 20 |
| core | 1.00 | 0.91 | 20 |
| lean | 1.00 | 0.97 | 20 |
| pack | 1.00 | 0.84 | 20 |

| refactor | files | tests | runs |
|---|---:|---:|---:|
| plain | 0.87 | 0.94 | 15 |
| core | 0.86 | 0.94 | 15 |
| lean | 0.90 | 0.93 | 15 |
| pack | 0.88 | 0.95 | 15 |

Graph tools called (all runs):

- **plain**: $2.36 in all; none
- **core**: $2.36 in all; `callers` 35, `tests_for` 13, `tests_to_run` 8
- **lean**: $1.96 in all; `callers` 44, `tests_for` 27, `tests_to_run` 5
- **pack**: $1.47 in all; none
