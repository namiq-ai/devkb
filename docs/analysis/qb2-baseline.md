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

## Result
| arm | R@1 | R@5 (90% interval) | R@10 | MRR | owner-file recall at 5 |
|---|---|---|---|---|---|
| bm25 | 0.26 | **0.56** (0.47-0.66) | 0.71 | 0.40 | 0.45 |
| structural | 0.21 | 0.44 (0.34-0.53) | 0.64 | 0.33 | 0.44 |
| hybrid | 0.25 | 0.56 (0.47-0.66) | 0.78 | 0.40 | 0.45 |
| popularity prior alone (earlier follow-ups first) | | 0.41 | 0.60 | | |

## Reading
- **The gate fails.** The design asked the combined arm to beat the text baseline by 10 points of recall at 5; it ties it (0.56).
  At 10 the hybrid is 7 points ahead (0.78 against 0.71), inside the noise of 73 items.
- **The structural signal is there but does not discriminate.** For 68 of 73 items, the files the query's names map to overlap the
  parent's files, yet that ranks the parent first only 21% of the time: a handful of files (`devkb/packs.py`, `process_api.py`)
  are touched by most issues, so overlap is common to many candidates.
- **The benchmark has a popularity artifact.** 27 parents account for all 73 items and the most-followed (#162) is the truth of 12
  (16%). Ranking older issues by how often they were followed already reaches 0.41 at 5. Text adds about 15 points over that;
  the graph arm adds nothing at 5.
- **Owner files: no arm is better** (0.44-0.45). A top-5 list of related issues names about half the files the fix will touch.
- **Recall understates every arm equally**: only the explicit link counts, and an issue can be related to many it does not cite.
  Precision cannot be measured with this truth.

## Decision
The baseline is far from the ceiling (0.56), so there is headroom, but the graph arm as built does not supply it. Per the
loop, iterate once and decide on held-out items:
1. Split by time: tune on the first 50 items, evaluate on the last 23 (never looked at).
2. Replace the overlap sum with the same BM25 scoring over file sets (a file is a term, a candidate's files its document), and fuse
   with the popularity prior.
3. Gate on the held-out items: hybrid recall at 5 at least 10 points above bm25 on the same items. If it fails, park
   `ErrorSignature` and the issue-graph schema: the evidence says text and the existing ticket nodes are enough for triage.

## Limits
73 items; intervals are wide (bm25 0.47-0.66). Names are resolved in today's graph; candidate files use commits dated before the
item. Issues are this repository's own and many follow-ups were written by the review process, so their wording echoes the parent's.
