# Live agent benchmark in another repository: yaml-cpp, C++ (2026-11-21)

**Question.** Does devkb, and the version in PR #401, change what an agent spends or achieves on real C++ bug fixes, when the agent's `devkb` is the arm's code? The earlier live benchmark could not test this: on devkb's own tickets the agent's `devkb` is the checkout under edit (errata 2 of `workflow-router-benchmark.md`).

## Design
Six bug-fix commits from yaml-cpp's own history (a single source file each, in distinct modules: emitter, scanner, tags, Base64, `uint8_t`). A ticket is the fix commit: the base is its parent; the issue text describes the symptom and was written without the fix; the **hidden check** copies the fix commit's own test files over the agent's tree, builds, and runs the whole test binary (it passes only if the new tests and every older test pass). Each ticket was validated: the fix's tests fail at the base and pass at the fix. The agent works in a fresh clone with a one-commit history, so the fix cannot be read from `git log`. Same model (Sonnet), same prompt, same tools (Bash, Read, Edit, Write, Grep, Glob; no network, no push).

| arm | devkb the agent runs | commit |
|---|---|---|
| `none` | none on the PATH | - |
| `orig` | `origin/main` | `812c359` |
| `ship` | PR #401 | `f2fe934` |

Each devkb arm gets that commit's `devkb` (`bench/policy/toolenv.py`), its graph built by it, its `AGENTS.md` policy block (identical across the two arms, checked) and its guardrail hooks. 6 tickets x 3 arms x 5 reps = 90 runs, one shuffled batch, 4 in parallel. Harness: `bench/ext/extbench.py`; comparison: `bench/ext/compare.py`; rows: `bench/ext/results-yaml-cpp.jsonl`.

## Quality
**Every run passes the hidden check: 30 of 30 in each arm.** These fixes were easy for the agent with or without devkb (5 to 13 turns, $0.06 to $0.17), so the benchmark cannot separate the arms on quality.

## Efficiency (mean over the six tickets, each weighted equally)
| measure | none | orig | ship |
|---|---|---|---|
| turns | 8.2 | 9.0 | 8.4 |
| cost per run | $0.10 | $0.11 | $0.10 |
| context tokens | 199k | 233k | 215k |
| output tokens | 2.5k | 2.5k | 2.3k |
| search calls | 4.3 | 4.6 | 3.8 |
| read-type calls | 3.0 | 2.5 | 2.2 |
| devkb navigation calls | 0 | 0.10 | 0.50 |
| `pack` calls | 0 | 0 | 0.07 |
| runs that used devkb at all | 0% | 10% | 47% |

Paired differences (first minus second; 90% interval from resampling runs within each ticket, tickets weighted equally; bold = excludes zero):

| measure | ship - orig | ship - none | orig - none |
|---|---|---|---|
| turns | -0.6 (-1.3 to +0.1) | +0.2 (-0.4 to +0.8) | **+0.8 (+0.0 to +1.6)** |
| cost | -$0.01 (-0.01 to +0.00) | +$0.00 (-0.00 to +0.01) | **+$0.01 (+0.00 to +0.02)** |
| context tokens | -17k (-41k to +5k) | +16k (-1k to +34k) | **+34k (+11k to +60k)** |
| output tokens | **-0.3k (-0.5k to -0.1k)** | **-0.3k (-0.4k to -0.2k)** | -0.0k (-0.2k to +0.2k) |
| search calls | **-0.8 (-1.2 to -0.3)** | -0.5 (-1.0 to +0.0) | +0.3 (-0.2 to +0.8) |
| read-type calls | -0.4 (-0.9 to +0.1) | **-0.9 (-1.3 to -0.4)** | -0.5 (-1.0 to +0.1) |

Per ticket (pass / turns / cost $ / devkb navigation calls):

| ticket | none | orig | ship |
|---|---|---|---|
| y1 emitter anchor `~` | 5/5 / 5.4 / 0.06 / 0 | 5/5 / 6.0 / 0.07 / 0 | 5/5 / 5.8 / 0.07 / 0 |
| y2 multi-document tags | 5/5 / 12.2 / 0.13 / 0 | 5/5 / 12.8 / 0.14 / 0 | 5/5 / 11.4 / 0.13 / 1.0 |
| y3 tagged literal scalar | 5/5 / 11.8 / 0.14 / 0 | 5/5 / 13.2 / 0.17 / 0.6 | 5/5 / 12.6 / 0.16 / 0.6 |
| y4 `SetTag` handles | 5/5 / 8.0 / 0.10 / 0 | 5/5 / 8.8 / 0.11 / 0 | 5/5 / 8.4 / 0.10 / 0.6 |
| y5 Base64 padding | 5/5 / 5.6 / 0.07 / 0 | 5/5 / 6.0 / 0.07 / 0 | 5/5 / 5.4 / 0.06 / 0.4 |
| y6 `uint8_t` | 5/5 / 6.2 / 0.08 / 0 | 5/5 / 7.0 / 0.08 / 0 | 5/5 / 6.8 / 0.08 / 0.4 |

## Reading
- **No quality difference and no efficiency gain from devkb on these tickets.** The original devkb costs a little more than using none (+0.8 turns, +$0.01, +34k context tokens, +17%: the policy block and tool definitions). The PR's version removes most of that excess: against `orig` it uses 0.8 fewer search calls and 0.3k fewer output tokens, and its differences from `none` are within the noise; it is not better than none.
- **The agent barely uses devkb**: 47% of `ship` runs and 10% of `orig` runs ran it at all, almost always `symbol`; `pack` appears 2 times in 30 runs. The `pack` changes in the PR therefore had almost no chance to matter here. Why `ship` used devkb more than `orig` is not explained: the two arms get identical policy text and the PR changes none.
- **Devkb arms read less** (read-type calls -0.9 against none) but search about the same, so the turn count does not move.

## Limits
Six small tickets; 33 comparisons were made, so a few intervals that clear zero may be chance; only large effects could show with 5 reps per cell. Wall time (`none` 2.6 min, `orig` 4.4, `ship` 3.7) includes setup (graph build, policy files) and is not agent time. Yaml-cpp fixes of this size are not the navigation-heavy work devkb is meant for: a ticket that needs the agent to find a function across many files, or to know who calls it, would be a fairer test.
