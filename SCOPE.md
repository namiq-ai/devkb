# Scope of this repository

## Purpose

Two things, in one repository, because each is only credible with the other:

1. **devkb**, an independent component that any git repository can use: it extracts a software-process knowledge
   graph (code, tests, tickets, commits, specifications, configuration), and gives it to coding agents as
   pre-computed context packs or as tools over MCP.
2. **The study** behind the paper *Fewer Turns, Not a Better Graph: A Pre-Registered Study of Process Graphs for
   Coding Agents*: the frozen protocol, every analysis script, the raw runs, and the paper source, so that every
   number in the paper can be reproduced from this repository.

## Who it is for, and what each gets

| Reader | What they can do here |
|---|---|
| Practitioners running coding agents | Install devkb, build a graph of their repository, hand agents packs or an MCP server, and measure whether it pays on their own code with the same harness. |
| Researchers in empirical software engineering | Verify every number in the paper (`make verify`), re-analyse the raw runs, replicate on other repositories or models, extend the pre-registered protocol. |
| Tool builders (code-graph retrieval, agent context) | Reuse the edge-level audit (precision and recall of each relation against source truth), the coverage statement, and the pack format. |
| Benchmark authors | Reuse the source-derived truth generators: import-resolved callers, error-to-handler chains, ticket-to-code joins from git history, none of which reads the graph being tested. |

## Contributions to the community

1. **A cost-at-equal-quality protocol for agent tooling**: the same model in every arm, every arm in one shuffled
   session, held-out tasks, pre-registration. The study measured a 39% swing in the plain baseline between
   sessions on identical tasks, larger than many reported tooling effects; the protocol is the remedy.
2. **An open dataset**: 1,020 confirmatory runs, 120 ablation runs, 240 process-study runs and 461 exploratory runs,
   with cost, tokens, turns, tool calls and score per run; full answers for the public repositories.
3. **devkb**: a governed schema (20 node types, 30 relations), extractors for Python and TypeScript repositories,
   packs, a 24-tool MCP server and a 7-tool lean set, and a coverage statement on every list answer.
4. **Graph auditing as a practice**: measuring each relation of a code or process graph against truth computed from
   source, with the tools to do it (`devkb audit`, `devkb/edge_truth.py`).
5. **Negative and corrected results**, reported as such: the exploratory cost penalty and its three mechanisms, the
   failed process-join hypothesis, and the authors' own explanation withdrawn by the ablation.

## What is in

| Path | Content |
|---|---|
| `devkb/` | the component: extractors, graph model and index, process API, packs, MCP server, CLI, audit and coverage tools |
| `devkb/bench/` | the benchmark harness, task generators and truth generators used by the study |
| `skills/` | agent skills that tell an agent which devkb tool answers which developer task |
| `tests/` | the component's test suite (202 tests, fixture repositories only) |
| `study/paper/` | the paper source and PDF |
| `study/preregistration/` | the frozen protocol and addendum (byte-identical, SHA-256 recorded) and the deviations |
| `study/analysis/`, `study/results/` | the analysis scripts and their outputs |
| `study/tasks/` | tasks, truth and packs for the two public repositories |
| `study/runs/`, `study/exploratory/` | raw runs: full rows for the public repositories, per-run metrics for the internal ones; graph audit aggregates |

## What is out, and why

| Excluded | Reason |
|---|---|
| Source, graphs, tasks, answers and packs of the two internal repositories (A, B) | proprietary; their runs are released as metrics with pseudonymous task ids, which reproduce every analysis exactly |
| The UI-flow extractor and its graph bridge | not part of this component; removed entirely |
| The factory's project registry, dashboard, orchestrator and role tooling | devkb no longer depends on them: a repository path is enough |
| Any client or third-party project data | never part of the study |

## Integration contract

- `pip install "devkb[mcp] @ git+https://github.com/namiq-ai/devkb"`, then `devkb build --project .` in any git
  repository. No configuration is required;
  an optional `devkb.json` declares the ticket prefix, issue and specification folders, role profiles and frontend.
- devkb only reads the repository and runs `git`. It never executes the analysed repository's code unless that
  repository opts in with `"run_repo_scripts": true`.
- The graph lives in the repository's `.devkb/` folder; agents read it through `devkb pack`, `devkb query` or
  `devkb mcp`.

## Roadmap

| Phase | Status | Content |
|---|---|---|
| 0 | done, private | component decoupled from the factory; study export; verification of every result from the export |
| 1 | next | documentation per tool, `devkb.json` reference, an end-to-end example on a public repository, CI running the tests |
| 2 | before public | licence; removal of internal ticket references from code comments; patent-counsel review of disclosure timing; history scan |
| 3 | public | release, Zenodo DOI for the artifact, an anonymised mirror for double-anonymous review |

## Release gates (before this repository becomes public)

1. Patent counsel confirms that publishing the extraction and pack design does not affect pending filings.
2. A licence is chosen (proposal: Apache-2.0 for code, CC BY 4.0 for data and paper text).
3. `study/` is re-exported and passes the denylist scan; the whole git history is scanned, not only the tip.
4. For double-anonymous review, reviewers get an anonymised mirror, not this repository.
