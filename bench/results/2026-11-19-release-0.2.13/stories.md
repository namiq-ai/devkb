# Before/after through SPEC-DKB-007 S1–S5 (0.2.13 chain, tri-mode runs)

162 runs recounted from their transcripts. Level = the newest story merged into main's devkb in that batch.

## Per level: averages per run, main arm against release (v0.2.12) in the same batches

| Level | Tickets | Arm | Runs | Pass | Cost $ | Min | Model calls | Context k tok | Output k tok | grep | devkb nav | devkb self-tests | Read | Hook answers | Hook pass-through | Answer chars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pre-S1 | #194, #195, #214 | nonekeep | 9 | 8/9 | 0.37 | 4.0 | 17.4 | 848 | 12.6 | 6.3 | 0.00 | 0.1 | 4.4 | 0.0 | 0.0 | 0 |
| pre-S1 | #194, #195, #214 | release | 9 | 9/9 | 0.32 | 3.5 | 13.7 | 640 | 10.9 | 4.8 | 0.00 | 0.4 | 4.1 | 1.1 | 1.3 | 2122 |
| pre-S1 | #194, #195, #214 | main | 9 | 8/9 | 0.34 | 3.9 | 15.2 | 722 | 11.2 | 4.8 | 0.00 | 0.2 | 4.3 | 0.7 | 1.8 | 1136 |
| S1 | #215 | nonekeep | 3 | 3/3 | 0.35 | 3.4 | 16.3 | 734 | 11.0 | 5.3 | 0.00 | 5.0 | 2.3 | 0.0 | 0.0 | 0 |
| S1 | #215 | release | 3 | 3/3 | 0.38 | 3.3 | 16.0 | 767 | 11.9 | 5.0 | 0.00 | 3.3 | 3.3 | 2.0 | 0.3 | 3679 |
| S1 | #215 | main | 3 | 3/3 | 0.33 | 3.9 | 16.0 | 681 | 10.0 | 4.0 | 0.00 | 6.0 | 3.3 | 2.7 | 0.7 | 4348 |
| S2 | #193, #216 | nonekeep | 6 | 2/6 | 0.87 | 11.7 | 36.2 | 2921 | 28.4 | 9.8 | 0.00 | 1.0 | 9.2 | 0.0 | 0.0 | 0 |
| S2 | #193, #216 | release | 6 | 3/6 | 0.96 | 13.8 | 35.3 | 3060 | 33.1 | 10.0 | 0.00 | 1.8 | 6.8 | 1.2 | 3.5 | 2388 |
| S2 | #193, #216 | main | 6 | 3/6 | 1.07 | 10.6 | 41.2 | 3777 | 34.3 | 12.8 | 0.00 | 1.5 | 8.3 | 1.3 | 3.3 | 1578 |
| S3 | #128, #189, #192, #196, #198, #201, #204, #212, #217, #228 | nonekeep | 30 | 20/30 | 0.25 | 3.7 | 16.4 | 641 | 5.9 | 5.2 | 0.00 | 0.1 | 4.7 | 0.0 | 0.0 | 0 |
| S3 | #128, #189, #192, #196, #198, #201, #204, #212, #217, #228 | release | 30 | 25/30 | 0.26 | 5.4 | 16.4 | 634 | 6.6 | 4.2 | 0.00 | 0.1 | 4.9 | 0.9 | 1.7 | 1155 |
| S3 | #128, #189, #192, #196, #198, #201, #204, #212, #217, #228 | main | 30 | 24/30 | 0.23 | 4.2 | 15.1 | 564 | 5.7 | 4.1 | 0.00 | 0.1 | 4.8 | 0.8 | 1.4 | 394 |
| S5 | #182, #187 | nonekeep | 6 | 5/6 | 0.28 | 4.6 | 19.2 | 749 | 7.5 | 7.7 | 0.00 | 0.0 | 4.2 | 0.0 | 0.0 | 0 |
| S5 | #182, #187 | release | 6 | 4/6 | 0.29 | 6.2 | 17.8 | 737 | 7.5 | 5.5 | 0.00 | 0.0 | 5.2 | 1.8 | 1.5 | 2683 |
| S5 | #182, #187 | main | 6 | 5/6 | 0.27 | 4.7 | 16.0 | 627 | 7.4 | 6.2 | 0.00 | 0.0 | 3.0 | 0.5 | 3.0 | 205 |

## Main against release, paired by ticket (ratio of per-ticket means; 1.00 = same)

| Level | Tickets | Cost | Context | Model calls | grep calls | Pass main | Pass release |
|---|---|---|---|---|---|---|---|
| pre-S1 | 3 | 1.07 | 1.15 | 1.13 | 1.09 | 8 | 9 |
| S1 | 1 | 0.86 | 0.89 | 1.00 | 0.80 | 3 | 3 |
| S2 | 2 | 1.08 | 1.21 | 1.17 | 1.38 | 3 | 3 |
| S3 | 10 | 0.92 | 0.92 | 0.94 | 0.98 | 24 | 25 |
| S5 | 2 | 0.92 | 0.85 | 0.90 | 1.12 | 5 | 4 |

## Hook intents seen by the main arm, per level (share of logged decisions)

- **S1** (10 decisions): call-sites 30%, locate 30%, read-body 30%, in-file 10%
- **S2** (29 decisions): read-body 34%, call-sites 24%, unknown 14%, call-sites-filtered 14%, locate 10%, in-file 3%
- **S3** (69 decisions): call-sites 30%, read-body 22%, locate 17%, in-file 16%, unknown 6%, list-files 4%, call-sites-filtered 4%
- **S5** (21 decisions): read-body 48%, locate 19%, call-sites 14%, in-file 14%, list-files 5%
