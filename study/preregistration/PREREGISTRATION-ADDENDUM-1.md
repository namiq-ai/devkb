# Pre-registration addendum 1: ablation of content vs. coverage, and a process-layer study

Frozen before any code, task or run of either study existed. Its SHA-256 and time are in
`PREREGISTRATION-ADDENDUM-1.sha256`. It does not change the main pre-registration; both studies are **secondary**.

## S1. Ablation: did the audit or the coverage statement remove the cost penalty?

The exploratory step E4 → E5 changed two things at once: the graph's content (audit, ODSF-314) and a coverage
statement on every list answer (ODSF-313). This 2×2 separates them.

- **Factors**: graph G0 = pre-audit snapshot of Repository A (ODSF-313 extractors, before ODSF-314), G1 = audited
  snapshot (ODSF-314); coverage C0 = coverage field removed from every tool reply, C1 = present.
- **Arm**: core (12 single-question tools), the arm whose E4 → E5 change motivated the claim. Plain is the shared
  baseline.
- **Tasks**: the six exploratory Repository A tasks (`2026-11-14-workflow-oco-tasks.json`), so the result speaks to
  the E4 → E5 claim directly. Sonnet, 4 repetitions per cell, same harness, turn cap and seed rule.
- **Outcomes**: cost effect against plain and score, per cell, as in the main study.
- **Analysis**: main effect of content = mean of (G1 − G0) over C; of coverage = mean of (C1 − C0) over G;
  interaction = (G1C1 − G0C1) − (G1C0 − G0C0); bootstrap 95% intervals resampling runs within task. Descriptive,
  no hypothesis test; the paper's sentence on content vs. tool design is rewritten to whatever this shows.

## S2. Process-layer study: does the graph pay on joins across tickets, commits, code and tests?

Every confirmatory task is a code-structure task. The process layer, the paper's distinctive part, has only
exploratory evidence. These tasks join process artifacts, which plain search answers in several steps.

- **Kinds**:
  - **ticket → code → tests**: for a ticket, the functions its commits changed and the test files that call them.
  - **commit → trace** (Repository B only, which records `## Trace`): for a commit, its ticket, the ticket's epic
    and specification.
- **Truth**: from git and the source, never from the graph. Commits are found by `git log --grep` on the ticket id;
  changed functions are the module-level functions and methods whose line ranges intersect the diff hunks at that
  commit; test files are those whose functions call a changed function by import-path resolution
  (`module_truth.py`); the trace comes from the ticket file's `## Trace` table.
- **Selection**: tickets whose commits change 2 to 12 functions in non-test Python files, at least one with a test
  caller; seed 2028; up to 4 tasks per kind per repository; Repositories A and B (the public repositories keep their
  tickets outside the repository).
- **Arms**: plain, core (which has `sdlc_context`, `lineage`, `review_pack`), and pack (a ticket pack written from
  the ticket id alone: commits, changed functions with their lines, tests, trace). Sonnet, 5 repetitions.
- **Outcomes and analysis**: as the main study; **H6**: pack costs less than plain on these tasks, quality
  non-inferior (margin 0.05), one-sided Wilcoxon over tasks; reported separately from H1–H5.

## Code

Both studies run on a separate branch, so the main study's frozen code is untouched while it runs. The only system
changes are a bench-only switch that removes the coverage field (S1) and the ticket pack (S2).
