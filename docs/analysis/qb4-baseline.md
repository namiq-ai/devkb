# QB4 baseline: from an epic's text, does a method predict the code a ticket will touch? (2026-11-21)

Design: `docs/specs/quality-benchmarks.md`. Tool: `bench/quality/qb4_epic.py`. No model runs.

## Setup
26 tickets whose body names a SPEC id that has a document under `docs/specs/` (SPEC-DKB-004 8, -005 4, -006 4, -007 10; -008 has two
tickets and no commit that changes a code file). Leave one ticket out: each is predicted from **its title and its spec's text**; its body,
which names files, is never used. Truth: the Python files under `devkb/` and `scripts/` changed by the commits that cite the ticket
(median 1.5 per ticket). Candidates: the 74 such files as they are today (so a name the fix added is visible to every arm).
Arms: bm25 (a file is its path words and the names defined in it; the title weighted threefold plus the spec text), grep (a file
scored by how many of the title's identifier-like words it contains), graph (names in the title, and weaker in the spec, resolved to
files, plus the files that call into them).

## Result (90% intervals resample the four specs)
| arm | recall@10 | recall@20 | precision@10 |
|---|---|---|---|
| bm25 | 0.83 | **0.95** (0.88-1.00) | 0.16 |
| grep | 0.91 | **0.96** (0.90-1.00) | 0.18 |
| graph | 0.84 | 0.84 (0.62-1.00) | 0.14 |

Paired recall@20: graph - bm25 -0.11 (-0.26 to 0.00); graph - grep -0.12 (-0.27 to 0.00); bm25 - grep -0.01. A popularity prior (the
files other items touch most, in-sample so an upper bound for a real prior) reaches 0.95 at 10 and 1.00 at 20.

## Reading
- **The benchmark saturates.** The truth is concentrated: three files (`scripts/devkb_guardrail.py`, `devkb/read_tools.py`,
  `devkb/process_api.py`) carry 32 of the 60 truth entries, and there are only 74 candidates, so any reasonable top 20 contains the
  answer. Plain text over file paths and names, or a grep of the title, reaches 0.95 or more.
- **The graph arm is not better; it is slightly worse** (0.84, interval touching 0.62-1.00). Resolving names to files and adding callers
  spreads weight to files the ticket did not touch.
- **What this cannot show:** with this repository's size and concentration, nothing could. A claim about impact subgraphs on a
  repository with thousands of files and a ticket touching a handful needs such a repository.

## Decision
The loop's rule is that a baseline at or above 0.9 closes the item: **do not build `GOVERNS`, `DEPENDS_ON` subgraph extraction or
other epic-impact schema on this evidence.** Revisit only with a larger repository (the C/C++ corpora, whose tickets can be built from
their own history) where the baseline leaves room.
