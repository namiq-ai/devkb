# PR #401 reviewed two ways: with and without devkb (2026-11-21)

Step 3 of the per-ticket checklist (AGENTS.md): review the PR with and without devkb's `review_pack`. Tool: `bench/review/review_bench.py`; known defects: `bench/review/pr401-known.json`; adjudication of the rest: `pr401-adjudicated.json`; rows: `results-pr401.jsonl`.

## Design
The subject is PR #401 as it stood **before** its review fixes (head `65fba22`), in a clean checkout whose history is two commits (the PR's base and the PR), so `git diff HEAD~1 HEAD` is the PR and no later commit can leak a fix. Scope: product code (`devkb/`, `scripts/`, `plugins/`) and harness code in `bench/policy/*.py`, including the acceptance scripts the PR can break without editing. Same prompt and read-only tools in every arm (no Edit or Write, no `gh`, no network), `AGENTS.md`, `CLAUDE.md` and `.claude/` removed, a cost cap of $8 per review, Sonnet.

| arm | what differs |
|---|---|
| `nodevkb` | devkb's own command blocked. **Confounded**: the repository under review is devkb, so 2 of 3 reviewers ran `python -m devkb.cli pack ...` on the checkout or a copy of it |
| `nocli` | the controlled no-devkb arm: no `devkb` and no `python -m devkb...` against the repository under review (running the code under review on fixtures elsewhere is allowed); 0 of 3 reviews used devkb |
| `devkb` | `devkb` (`origin/main`) on the PATH and a graph of the PR's tree; told how to use `pack file`, `pack refactor`, `symbol`, `outline`, `uses` |

3 reviews per arm, 9 in all. **Quality** is scored against 15 defects in scope (1 blocker, 9 should-fix, 5 nits), every one reproduced and fixed afterwards (they come from earlier reviewers, who did not use devkb). A finding matches one when its file and its wording match (tightened after a first pass over-credited two of them); the findings that match none were each adjudicated by running or reading them (10 real, 2 false).

## Quality
| arm | known defects found (of 15) | blocker found | should-fix (of 9) | nits (of 5) | findings per review | new real per review | false per review | total real per review |
|---|---|---|---|---|---|---|---|---|
| `nodevkb` | 4.7 | 1/3 | 3.3 | 1.0 | 8.0 | 3.0 | 0.0 | **7.7** |
| `nocli` | 5.0 | 3/3 | 3.3 | 0.7 | 5.7 | 0.7 | 0.3 | 5.7 |
| `devkb` | 4.0 | 3/3 | 2.0 | 1.0 | 4.0 | 0.0 | 0.0 | 4.0 |

## Efficiency
| arm | turns | cost | context tokens | output tokens | wall time | cost range | cost per real finding |
|---|---|---|---|---|---|---|---|
| `nodevkb` | 25.0 | $0.59 | 1529k | 14.6k | 3.6 min | $0.48-0.77 | $0.08 |
| `nocli` | 23.0 | $0.51 | 1328k | 11.2k | 3.4 min | $0.40-0.70 | $0.09 |
| `devkb` | **17.0** | **$0.35** | **851k** | **6.6k** | **2.5 min** | $0.33-0.39 | $0.09 |

## Per known defect (reviews that found it)
| defect | `nodevkb` | `nocli` | `devkb` |
|---|---|---|---|
| H1 blocker: the acceptance scripts stub `template_for`/`checkout` with the old signature | 1/3 | 3/3 | 3/3 |
| P2 the task hint is cached for the life of a long-lived reader | 3/3 | 3/3 | 3/3 |
| P3 the mention scan matches common names | 3/3 | 3/3 | 3/3 |
| P7 `init` silently removes an installed prompt hook | 3/3 | 2/3 | 3/3 |
| P4 the router creates `.devkb` in a project with no graph | 0/3 | 1/3 | 0/3 |
| H4 `grep_patterns` misreads options and wrappers | 2/3 | 0/3 | 0/3 |
| H2 replayed commands go through a shell | 1/3 | 0/3 | 0/3 |
| H6 `--compare` counts unknown cost as $0 | 1/3 | 1/3 | 0/3 |
| H8, H9 | 0/3 | 1/3 each | 0/3 |
| P1, P5, P6, H3, H5 | 0/3 | 0/3 | 0/3 |

Real defects found outside the list (all reproduced): the router treats `UTF-8`, `SHA-256`, `ISO-8601`, `#333` and `#000000` as ticket ids; `_grams` of a message with no letters returns `{''}`; `replay_queries.table()` crashes when there are no `symbol` queries; `inline_replay` divides by zero when no run matches; `policybench.finished()` raises on an empty `end` file; `prompt.sh`'s `exec ... || exit 0` exits 127 and pins a version above the package's; a backticked file name routes as a `navigate` subject; `devkb_targets` loses the target after a flag with a value. Two findings were not defects (an `init` substring match that is the intended one; an unguarded `.group(1)` that no real pack line can reach).

## Reading
- **Devkb reviews are the cheapest and the most predictable** ($0.35, range $0.33-0.39, against $0.51 and $0.59 with ranges more than ten times wider), and fastest in turns.
- **Cost per real finding is the same, $0.08-0.09, in all three arms**: devkb makes a review cheaper because it reports less, not because it finds the same for less.
- **The blocker:** devkb 3/3, controlled arm 3/3, confounded arm 1/3. With the controlled arm there is no devkb advantage; the confounded arm's 1/3 is a run-to-run spread.
- **Breadth:** the devkb reviews found nothing outside the known list; the other arms found 3.0 (confounded) and 0.7 (controlled) real defects per review beyond it.
- 7 of the 15 known defects were found by nobody, most of them in the harness and replay tooling.

## Limits
3 reviews per arm are too few for anything but large effects. The known-defect list came from reviewers who did not use devkb, so it may under-count what a devkb review finds (the adjudication of the rest is the check). The confounded arm used devkb by accident, which is why the controlled arm was added. The gate (`bench/review/gate.py`) was not run and no review was posted to GitHub.
