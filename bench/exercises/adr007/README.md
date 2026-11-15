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

| | Round 1 plain | Round 1 devkb | Round 2 plain | Round 2 devkb | Round 3 |
|---|---|---|---|---|---|
| devkb uses | — | **0** | — | **0** | running |
| Cost | $2.20 | $2.18 | $2.26 | $1.98 | |
| Wall time | 11:10 | 12:00 | 11:26 | 9:24 | |
| Turns | 57 | 86 | 64 | 61 | |
| Share of tool output spent reading code | 87% | 92% | 86% | 89% | |
| Tests at the end | 247 | 250 | 252 | 255 | |
| Offline links precision, lattice-scan / Mealie / Dispatch | 1.0 / 1.0 / 1.0 † | 1.0 / 1.0 / 1.0 | pending | pending | |
| GitHub layer on Mealie | did not finish in 50 min: rate limit | 6 min; 966 closing links, precision 1.0 | pending | pending | |
| GitHub client | REST, one request per pull request | GraphQL, ~100 per request | GraphQL | REST, one request per pull request | |
| Blind review prefers | | this one (~65%) | this one (~75%) | | |

† The check first scored Dispatch 0.96: the one link it called wrong is pull request 5395's own merge commit; the API
lookup had failed on the rate limit, which this branch had consumed. The plain branch's round-1 checks after the
timeout were run with `rest_plain.py` (the same functions, Mealie's online build recorded as timed out).

Raw results: `baseline.json`, `round*/acceptance-*.json`, `round*/process.jsonl`, `round*/summary-*.md` (each
agent's own final summary), `round*/review.md` (the blind reviews, with the key).

## Findings so far

1. **No agent used devkb** in rounds 1 and 2, with a tool table or with orientation tools offered. The work was
   reading how the code is written (86–92% of tool output), which the graph does not store, in a repository small
   enough (about 10k lines) to read; a detailed prompt and an ADR naming the files outweighed general instructions.
2. **The preferred implementation flipped between rounds** and followed the agent's design of the GitHub client
   (bulk GraphQL or a REST request per pull request), not the arm. With devkb unused, the difference between arms is
   run-to-run variation.
3. **The exercise does not measure devkb in use.** That is measured in `bench/results/` and the paper (35–51% cheaper
   on call-chain tasks when used). Round 3 tests whether a task-shaped trigger makes agents use it unprompted.
