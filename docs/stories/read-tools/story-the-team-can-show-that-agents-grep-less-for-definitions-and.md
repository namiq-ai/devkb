---
id: 12
type: story
title: "The team can show that agents grep less for definitions and outlines with no loss in score"
parent: epic-core-read-tools
covers: [R11]
after: [11]
hitl: true
risk: medium
---

# The team can show that agents grep less for definitions and outlines with no loss in score

## Description

D7: the success measure. A person runs two new feature builds with the four tools in `lean-pack` (an agent run is the person's step; it uses the local model policy of the factory, not a public API), then the grep-purpose analysis is rerun on their transcripts and compared with the nine baseline builds (275 greps; definition 14.7% and outline 11.9% of cost). The script `bench/exercises/cpp/grep_purposes.py` and the transcripts are not in this checkout (initiative assumption): the first step is to find them and commit their paths.

## Requirements

1. **The baseline is reproducible** (R11)
   **Given** the nine baseline transcripts
   **When** `python3 bench/exercises/cpp/grep_purposes.py <baseline dir>` runs
   **Then** it prints the purpose table of the analysis (275 greps; definition and outline shares) and the report records the command, the script's commit and the transcripts' location

2. **The after-run uses the same exercise on two builds** (R11)
   **Given** the same feature-build exercise and acceptance check, `lean-pack` with the four tools, two builds
   **When** the analysis runs on their transcripts
   **Then** the report gives, per build and pooled, the count and cost of definition greps and outline greps, and the tool calls of `symbol`, `outline`, `uses`, `search_docs`

3. **The fall is at least 60%** (R11)
   **Given** the baseline and the after-run
   **When** the report compares them
   **Then** it states definition-plus-outline greps fell by at least 60% (count and cost), or states by how much they fell and that the target was missed; it does not round up

4. **No loss in the acceptance score** (R11)
   **Given** the exercise's acceptance check run on all builds
   **When** the scores are compared
   **Then** each after-run score is at least the baseline mean, or the report says so and names the failing acceptance items

5. **The report names what agents still grep for** (R11)
   **Given** the after-run's remaining greps
   **When** they are classified by purpose
   **Then** the report lists the three largest remaining purposes with their share, as input to the owner's next decision (for example `find_code` in `dev`)

## Boundaries

- Must not change: the benchmark exercise, the acceptance check, the baseline transcripts.
- Not here: a claim about agent quality beyond the acceptance score.

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 10
- analysis — docs/analysis/read-tools-analysis.md, section 1

## Notes

- hitl: a person starts the two builds and supplies the transcripts; the factory's LLM-tier rules apply to the agent used.
- Open question: where `grep_purposes.py` and the nine transcripts are kept; the story's first step answers it.
- Check beyond the criteria: run the two builds in a fresh checkout so no earlier read of the files leaks in.
