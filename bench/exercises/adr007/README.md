# Exercise: implementing ADR-DEVKB-007 with and without devkb

**Question**: does an agent implementing a real feature in devkb do better when devkb is integrated into the
repository? Exploratory, one run per arm per round; the acceptance check was fixed and hashed before any run.

## Design

- **Task**: implement ADR-DEVKB-007 (pull requests and hosted issues) from the same starting commit, with the same
  prompt (`prompt.md`), model (Sonnet), tools and limits (`run_arm.sh`); both arms launched at the same second.
- **The only difference**: the devkb arm ran `devkb init` first (its setup commit is excluded from the comparison):
  - round 1: `AGENTS.md` table of the 7 lean tools, MCP server with the `lean` toolset;
  - round 2: the `dev` toolset (lean plus `explain_area`, `feature_brief`, `find_code`) and rows telling the agent to
    orient with them before writing code;
  - round 3: a task-shaped trigger, shell commands at each step of a change (`devkb pack file PATH` before editing a
    file, `refactor`/`change` before changing a function, `error` from an error message).
- **Judged by**:
  - `acceptance.py` (sha256 of the file as run in `acceptance.sha256`; this copy differs from it only in local paths,
    replaced by `<exercise>` and `bench-work`), written before the runs and applied unchanged: tests, schema,
    offline pull-request links against the GitHub API with no network allowed (strace), the opt-in GitHub layer on
    lattice-scan and Mealie, privacy, the `pr` pack, and the benchmark registry's pack check;
  - a blind review of the two diffs by a separate agent that saw only "A" and "B";
  - process metrics from the transcripts (`metrics.py`). A devkb "use" is an MCP call or a `devkb pack`/`query`
    command; a `devkb build` on a public checkout is the agent testing its own extractor, counted separately.

## Results

| | R1 plain | R1 devkb | R2 plain | R2 devkb | R3 plain | R3 devkb |
|---|---|---|---|---|---|---|
| devkb uses | — | **0** | — | **0** | — | **0** |
| Cost | $2.20 | $2.18 | $2.26 | $1.98 | $1.99 | $1.63 |
| Wall time | 11:10 | 12:00 | 11:26 | 9:24 | 11:37 | 7:52 |
| Turns | 57 | 86 | 64 | 61 | 56 | 43 |
| Share of tool output spent reading code | 87% | 92% | 86% | 89% | 92% | 95% |
| Tests at the end | 247 | 250 | 252 | 255 | 252 | 246 |
| Offline link precision (lattice-scan / Mealie / Dispatch) | 1.0 / 1.0 / 1.0 † | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| GitHub layer on Mealie | did not finish in 50 min (rate limit) | 6.0 min; 966 closing links, 1.0 | 5.2 min; 966, 1.0 | 17.5 min; **88 closing links, 0.28** | 23 min ‡; 966, 1.0 | 8.2 min; 966, 1.0 |
| Acceptance check | fail | **pass** | **pass** | fail | **pass** | **pass** |
| Blind review | pair: lost | pair: won (~65%) | pair: won (~75%) | pair: lost | final: 2nd | final: 3rd |
| Final four-way ranking | | **1st** | 4th | | 2nd | 3rd |

† The check first scored Dispatch 0.96: the one link it called wrong is pull request 5395's own merge commit; the API
lookup had failed on the rate limit. ‡ Measured while two other checks shared the GitHub API.

**Merged**: round 1's devkb arm, ranked first in the final blind ranking (`final/ranking-review.md`), after fixing the
defects its reviewer marked certain (plus the possible ones), with a test each. The merged code passes the same
acceptance check (`final/acceptance-merged.json`): 260 tests, offline precision 1.0 on all three repositories, recall
1.0 on lattice-scan, no network by default, Mealie's GitHub layer in 5.0 min with 966 closing links at precision 1.0,
the `pr` pack, privacy, and no regression in the registry's pack check.

Raw results: `baseline.json`, `round*/acceptance-*.json`, `round*/process.jsonl`, `round*/summary-*.md` (each agent's
own final summary), `round*/review.md` and `final/ranking-review.md` (the blind reviews, with their keys).

## Findings

1. **No agent used devkb in three rounds**, with a tool table, with orientation tools, or with a step-by-step trigger
   (`devkb pack file PATH` before editing a file). The work was reading how the code is written (86–95% of tool
   output), which the graph does not store, in a repository small enough (about 10k lines) to read; a detailed prompt
   and an ADR naming the files outweighed every form of instruction in `AGENTS.md`.
2. **The quality of an implementation followed the agent's design, not the arm.** Every run that chose one REST
   request per pull request failed at scale or lost closing links; the bulk GraphQL designs passed. The preferred
   arm flipped between rounds. With devkb unused, the difference between arms is run-to-run variation; the cost
   differences are too ($1.63 to $2.26 across runs that never touched the graph).
3. **The exercise did not measure devkb in use.** That is measured in `bench/results/` and the paper: 35–51% cheaper
   on call-chain tasks when the agent uses it.
4. **What did decide quality** was evidence the agents never saw: a pre-registered acceptance check against the real
   API, and blind review. Two of six implementations that passed their own test suites failed at scale, and the
   reviewers' "certain" defects were confirmed by measurement (request-per-PR timeouts, 0.28 closing-link precision).
