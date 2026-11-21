# QB2 baseline: does a method find the issue a new one follows? (2026-11-21)

Design: `docs/specs/quality-benchmarks.md`. Tool: `bench/quality/qb2_related.py`. No model runs.

## Setup
222 issues of this repository. **73 items**: issues that say "Follow-up of #N" or "duplicate of #N" with N an older issue
(all 73 have exactly one parent; 27 distinct parents). The query is the issue's title and body with every `#number` and "issue N"
removed. Candidates: every older issue (median 121). Truth: the parent. Arms:

- **bm25**: text retrieval over title and body (identifiers split at `_` and case changes).
- **structural**: the code names and paths in the query, resolved in the graph to files (a name counts when it has at most 4
  definitions), matched against each candidate's files, weighted by how rare the file is. A candidate's files are those changed by
  commits that cite it **before the item was filed**, plus the files its own text names.
- **hybrid**: reciprocal-rank fusion of the two.
- Owner-file recall: the files changed by the item's own fix (commits after it was filed) against the files of the arm's top 5 candidates (49 items have such commits).

## Result (corrected 2026-11-21 after an independent audit)
The first version resampled the 73 items as if independent, parsed multi-line commit messages wrongly (junk in the owner-file
sets) and carried a popularity prior that the script did not produce. Now: intervals resample the 27 parents; commits are parsed
with record separators and committer time; two priors are arms (causal: issues earlier items followed; leave-one-out: every other
item, which is not causal and is shown only to bound the artifact).

| arm | R@1 | R@5 (90%, resampling parents) | R@10 | MRR | owner-file recall at 5 |
|---|---|---|---|---|---|
| bm25 | 0.26 | **0.56** (0.43-0.70) | 0.71 | 0.40 | 0.44 |
| structural | 0.19 | 0.44 (0.32-0.59) | 0.63 | 0.32 | 0.42 |
| hybrid (bm25 + structural) | 0.25 | 0.56 (0.45-0.71) | 0.78 | 0.40 | 0.44 |
| prior, causal | 0.14 | 0.41 (0.19-0.56) | 0.60 | 0.28 | 0.31 |
| prior, leave-one-out | 0.16 | 0.58 (0.33-0.74) | 0.73 | 0.35 | 0.31 |
| bm25 + causal prior | 0.33 | 0.63 (0.47-0.75) | 0.84 | 0.48 | 0.41 |

Paired differences in R@5 (90%, resampling parents): hybrid - bm25 **+0.00 (-0.07 to +0.08)**; bm25 - causal prior +0.15 (-0.08 to
+0.47); bm25 + prior - bm25 +0.07 (-0.11 to +0.18); bm25 - leave-one-out prior -0.01 (-0.26 to +0.35).

**The 27 items whose parent no earlier item followed** (a prior has nothing to count; this is the slice where the method must find
the parent from the issue's own words): bm25 **0.78**, structural 0.59, hybrid 0.78, causal prior 0.00, bm25 + prior 0.37.

## Reading
- **The gate fails and stays failed.** Hybrid against bm25 is +0.00 with an interval of about plus or minus 0.08. Adding the graph's
  structural arm adds nothing to text.
- **The all-items number mixes two tasks.** 46 items repeat a parent that earlier items already followed, where a popularity
  signal helps (a leave-one-out prior alone reaches 0.58, level with bm25); 27 do not. On those 27, text reaches 0.78 and the
  structural arm 0.59: the graph arm is the weaker one.
- **The structural signal exists but does not discriminate**: for 68 of 73 items the query's files overlap the parent's, yet a few
  files (`packs.py`, `process_api.py`) are common to most issues.
- **Owner files:** no arm is better (0.42-0.44), and the priors are at 0.31.
- Recall understates every arm equally: only the explicit link counts, and precision cannot be measured with this truth.

## Decision
Per the loop's rule ("park if the hybrid does not beat text by 10 points"): **park `ErrorSignature` and the issue-graph schema.**
Text over the existing ticket and issue text is enough for related-issue retrieval here, and the structural arm is worse on the
slice that tests it. A popularity prior combined with text may add a few points (+0.07, not distinguishable from zero); it is a
ranking choice for a triage tool, not a graph feature. Revisit only with a different truth (real duplicates; there are 3).

## Limits
73 items from 27 parents; intervals are wide even after resampling parents. Names are resolved in today's graph; candidate and
query text are today's GitHub bodies (an edit after filing would not show). Issues are this repository's own and many follow-ups
were written by the review process, so their wording echoes the parent's.
