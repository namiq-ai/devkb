# Performance: v0.2.6 against main (2026-11-16)

Question: did the read tools (#39), the language profiles (#41) and the pre-edit hook (#42) make devkb slower or heavier?
Method: `bench/perf.py` builds each repository's graph three times and times five command-line queries; `bench/perf_compare.py` compares two runs. The same machine ran everything one pass after another, never at the same time. The same code was measured twice (the second pass of `main`) to find the noise.
Repositories: click (179 files), mealie (1,781), prefect (5,542), leveldb (154), fmt (148), Zephyr (70,856 files, 15,912 of them C/C++).

## Noise

The same code, run twice: short builds differ by up to **15%** (click 12.9 and 14.9 s, mealie 65.9 and 73.2 s); Zephyr differed by 3% and every size by 0%. Query latencies of 0.15 to 0.4 s differ by up to 25%, so a query difference under 0.05 s is not a finding.

## Result

| Repository | Build s (v0.2.6 → main) | Peak MB | Graph MB |
|---|---|---|---|
| click | 16.0 → 12.9 and 14.9 | 58 → 57 | 6.4 → 6.4 |
| mealie | 67.5 → 65.9 and 73.2 | 164 → 165 | 26.1 → 26.1 |
| prefect | 195 → 190 and 195 | 602 → 603 | 129.1 → 129.1 |
| leveldb | 1.2 → 1.3 | 41 → 40 | 3.7 → 3.8 |
| fmt | 2.0 → 2.3 and 2.2 | 51 → 50 | 5.5 → 5.7 |
| **Zephyr** | **124.7 → 150.7 and 146.4 (+17 to +21%)** | **1,419 → 1,683 (+19%)** | **325 → 425 (+31%)** |

Query latency (command line, median of five, including interpreter start and graph load): unchanged within noise on click, mealie, prefect, leveldb and fmt (pack file 0.14-0.53 s, pack change 0.15-0.55 s, query about 0.14-2.6 s).
On Zephyr: pack file 1.19 → 1.24 s, pack change 1.12 → 1.25 s, **query about 5.6 → 7.7 s (+37%)**: the graph is 31% bigger and is read on every command-line call.
The new read tools on Zephyr, command line (cold): symbol 3.1 s, outline 1.6 s, uses 4.0 s; in an MCP server the graph is loaded once, and the warm calls took 30 to 500 ms (uses 0.8 to 1.5 s).

## Where the Zephyr growth comes from

`.devkb/symbols-edges.jsonl` 83 → 115 MB, `symbols-nodes.jsonl` 76 → 94 MB. By kind:

| | v0.2.6 | main |
|---|---|---|
| DECLARES edges | 0 | 82,261 |
| READS edges | 0 | 51,994 |
| ConfigKey nodes | 0 | 36,638 |
| File nodes | 13,140 | 31,292 |
| CALLS edges | 145,404 | 149,714 |
| Symbol nodes | 147,307 | 147,374 |

The growth is the output of SPEC-DKB-002 (language profiles): declarations of C/C++ symbols, reads of configuration keys (Kconfig, `CONFIG_*`) and the header and Kconfig files they sit in. It is a deliberate cost of a new feature, not an accident; the call graph is unchanged. Python and the small C++ repositories show no change because they carry few declarations and no Kconfig.
Open: the build is +17% on Zephyr (146 s here on a busy machine, 95.5 s on a quiet one; the budget is 120 s); the graph load makes every cold command-line query on a very large repository slower. A cheaper `DECLARES` encoding (one edge per declaration kind) or lazy loading of the edge file would address it; not done.

## The skill configuration and tool search

Claude Code defers MCP tools behind a `ToolSearch` call; in 15 of 16 devkb runs it was the first call, a whole turn spent before the first lookup. The workflow benchmark's forced prompt even said "load them with ToolSearch if they are not yet loaded".
Documented controls (code.claude.com/docs/en/mcp): `"alwaysLoad": true` on a server entry, and `_meta: {"anthropic/alwaysLoad": true}` on a tool in `tools/list`. A skill cannot change this (its description is always in context, its body loads when invoked, and the docs say nothing about a skill's mention loading an MCP tool). A plugin cannot set `ENABLE_TOOL_SEARCH` (it is a session setting), and setting it to `false` also loads Claude Code's own built-in tools (about 18k tokens).
Change: `symbol`, `outline` and `pack` carry `_meta anthropic/alwaysLoad`, so they load with the prompt and the other tools stay deferred; no setting, no skill edit, works for every install of the server.

Measured (multi-hop questions about click, 16 runs, default Claude Code settings, the plugin's `lean-pack` toolset):

| Arm | F1 (corrected) | Turns | Model calls | ToolSearch as first call | Cost per run |
|---|---|---|---|---|---|
| plain | 0.878 | 4.12 | 3.75 | n/a | $0.0456 |
| devkb, tools deferred (before) | 0.889 | 4.19 | 4.06 | 15 of 16 | $0.0474 |
| **devkb, alwaysLoad (after)** | 0.876 | **3.25** | **3.12** | **0 of 16** | **$0.0430** |

Turns fall 22% against the deferred arm and 21% against plain; cost is 6% below plain (it was 4% above). 16 runs per arm: a direction, not a proof.

### The apparent score drop was the scorer

The first scorer gave 0.772 (plain), 0.764 (deferred) and 0.753 (alwaysLoad), which looked like a drop. It was not one:
- **Recall is the same in every arm**: all 72 callees (4 to 6 per question, 16 runs) were found with the right first line, by plain, deferred and alwaysLoad alike.
- **The difference was in the precision term.** The first scorer counted a repository-defined name in the answer as wrong when it was not in its list of the function's callees. That list left out every callee whose name several classes share (`consume_value`, `process_value`, `get_parameter_source` for `handle_parse_result`), so answers that named them correctly were marked down, and so were class names used as qualifiers (`Command.format_help`) and words in prose (`read`, `function`). The three arms each had 49 to 53 such names over 16 runs: noise in a flawed term.
- **Rescored** (`bench/readtools/hop_rescore.py`: truth = every defined name the function calls; class qualifiers not counted): F1 plain 0.878, deferred 0.889, alwaysLoad 0.876. Paired difference alwaysLoad minus plain: **-0.003, 95% interval [-0.036, +0.032]** (16 pairs). There is no measurable score change.
- One `nav` run (M1) scored recall 0.75 because it gave the constructor's line (`__init__`) for three classes it constructs, where the truth wanted the `class` line; a valid reading, not a miss.

## What changed in the benchmark workflow

- `bench.yml` job `perf` (free, on pull requests that touch `devkb/**`): builds click and fmt with the previous release and with the checkout on the same runner and fails when a build is over 1.5 times or a query over 2 times and 0.05 s slower.
- Agent arms: `nav` (symbol, outline, pack) added; `lean-pack` is the plugin's toolset.
- `workflow_run.py` no longer tells the agent to load tools with ToolSearch; it records `tool_search` and `first_tool` for every run, and the report prints a "ToolSearch turns" table per arm, so a regression of this kind shows.
