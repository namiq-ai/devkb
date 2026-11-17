# Tool mix of the audit and fix agents (2026-11-17), from their transcripts by `toolmix.py`

Transcripts are not committed (they hold local paths); the classes are defined in `toolmix.py`.

| transcript | devkb queries | devkb calls (k chars) | search calls (k chars) | read calls (k chars) | run calls (k chars) | other calls (k chars) | devkb share of navigation calls | devkb share of navigation text |
|---|---|---|---|---|---|---|---|---|
| audit 1, C/C++ (devkb asked mid-run) | 2 | 1 (1.5) | 1 (0.8) | 10 (149.8) | 8 (6.0) | 1 (0.1) | 8% | 1% |
| audit 1, C# (mid-run) | 8 | 4 (9.5) | 4 (23.7) | 9 (153.1) | 4 (1.8) | 1 (0.1) | 24% | 5% |
| audit 1, tools (mid-run) | 6 | 2 (4.3) | 5 (15.4) | 10 (108.0) | 3 (2.5) | 1 (0.1) | 12% | 3% |
| audit 2, plugin (devkb-first) | 23 | 9 (24.6) | 9 (20.7) | 5 (32.7) | 3 (4.3) | 3 (0.7) | 39% | 32% |
| audit 2, C# (devkb-first) | 19 | 8 (24.7) | 5 (12.1) | 13 (78.0) | 9 (3.2) | 1 (0.1) | 31% | 22% |
| fix, Python | 29 | 19 (35.1) | 27 (37.7) | 25 (122.6) | 32 (19.4) | 5 (8.2) | 27% | 18% |
| fix, C# | 18 | 10 (20.3) | 23 (32.2) | 24 (76.0) | 25 (11.7) | 7 (4.4) | 18% | 16% |
| fix, C/C++ | 13 | 4 (8.5) | 37 (44.0) | 19 (67.4) | 42 (43.0) | 4 (4.3) | 7% | 7% |
| fix 2, plugin/init/read tools | 15 | 10 (18.5) | 21 (46.8) | 11 (17.6) | 20 (6.9) | 4 (7.1) | 24% | 22% |
| fix 2, C# | 12 | 8 (16.0) | 29 (32.6) | 40 (120.9) | 31 (50.9) | 6 (5.7) | 10% | 9% |
| fix 2, C/C++ | 12 | 6 (13.2) | 43 (71.6) | 30 (72.6) | 34 (32.2) | 12 (2.5) | 8% | 8% |
