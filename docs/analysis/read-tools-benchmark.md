# Read tools: what the benchmarks show

Last run: 2026-11-16 on `main` at `fa6c892` (read tools #39, language profiles #41, pre-edit hook #42, always-loaded tools #46), against click.
Tools under test: `symbol`, `outline`, `uses`, `search_docs` (SPEC-DKB-003), served by the plugin's `lean-pack` toolset (12 tools; `symbol`, `outline` and `pack` load with the prompt).
Model: Sonnet in every arm. 16 runs per arm and configuration: directions, not proofs.

**0.2.8 (2026-11-18), not re-run:** this benchmark ran on `fa6c892`, the code 0.2.8 builds on. 0.2.8 changes what some
read tools answer, from the audit (`devkb-for-auditing.md`): paths under dot-directories resolve (#54); a rejected
`search_docs` pattern is an error, not "no match" (#55); `symbol`'s caller count leaves out a self-call (#70) and says
when it is partial (#87); `uses` ranks code before comments within its per-file cap (#89) and accepts a file for
`--under` (#90); `outline` pages with `offset` (#91). None of the 16 questions here touches a dot-directory, a rejected
pattern or a recursive function; the `uses` ranking can change which hits fill the cap on N5/N6 (the two `uses` questions). Turn and cost effects
are expected to be unchanged; this is a statement of what was not measured, not a result.

## Summary (devkb as shipped, against plain)

| Question set | Turns | Cost per run | Score |
|---|---|---|---|
| Navigation (8 questions, one lookup each), default settings | 2.4 → 2.1 (-12%) | $0.0096 → $0.0085 steady-state (-11%) | 0.96 and 0.96 |
| Multi-hop (find a function, list its callees with lines), default settings | 3.88 → 3.25 (-16%) | $0.0482 → $0.0438 (-9%) | F1 0.887 → 0.863 (paired -0.024, 95% interval [-0.073, +0.021]); recall 0.969 → 1.000 |
| Multi-hop, built-in tools restricted to `Read,Grep,Glob,Bash` | 4.44 → 3.38 (-24%) | $0.0237 → $0.0236 (0%); steady-state -9% | F1 0.885 → 0.902 (paired +0.017, interval [-0.016, +0.054]) |

- **Fewer turns is the robust effect.** The agent calls `symbol` first instead of a grep and a read, and it no longer spends a turn on `ToolSearch` (0 of 48 devkb runs began with it; 15 of 16 did before the tools were marked always-loaded).
- **Cost is lower by about 10% once the cache is warm, and flat or slightly higher in one-shot runs** (a cold prompt cache is paid once per run, and the devkb prompt is 2 to 3k tokens longer).
- **No measurable change in correctness.** All intervals include zero. The multi-hop precision is lower in the default configuration (0.835 → 0.794, not significant, not investigated).
- Not shown: a saving above about 10%, or any gain on questions that one grep already answers (N5 to N8: the agent used a grep in both arms).

## Method

- **Project and instruction:** click at a pinned commit; the devkb arm has `devkb init` output from the code under test (`AGENTS.md` block, `.mcp.json`) and a graph built by it; the plain arm has none of these.
- **Settings:** `default` is Claude Code with its own settings (tool search on); `lean` adds `--tools Read,Grep,Glob,Bash`, which removes the built-in tools' definitions (about 17k tokens) from both arms.
- **Questions, each with truth computed from the source** (`bench/readtools/nav_tasks.py`, `hop_tasks.py`): navigation asks for exact lines, a misspelled name, a class's methods, files using a constant, every reference, a doc heading, names by prefix; multi-hop asks for one function's callees (4 to 6) with their files and first lines.
- **Runs:** two repetitions of each question per arm, shuffled and run six at a time; read-only; all arms interleaved.
- **Scoring:** navigation by `bench/readtools/nav_score.py`; multi-hop by `hop_score.py`: recall (callee found with its first line = 1, name only = 0.5) and precision (a repository-defined name in the answer is right when the function calls it), F1 of the two. Differences are paired by question and repetition, with a bootstrap interval (`hop_rescore.py`).
- **Cost:** the reported `total_cost_usd`; "steady-state" prices the first model call's prompt as already cached, as in a running session (`cost_breakdown.py`; rates fitted to 84 reported costs with no error: input $2, cache write $4, cache read $0.10, output $10 per million tokens).

## 1. Navigation (8 questions, 2 repetitions, default settings)

| Question | Tool it exercises | Arm | Score | Turns | Model calls | Grep | File load | devkb | Text returned | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| N1 symbol: exact lines of a function | | plain | 1.00 | 3.0 | 3.0 | 1.0 | 1.0 | 0.0 | 2.4k | 74k / 0.3k | $0.034 |
| N1  | | devkb | 1.00 | 2.0 | 2.0 | 0.0 | 0.0 | 1.0 | 0.2k | 53k / 0.1k | $0.029 |
| N2 symbol: qualified method lines | | plain | 1.00 | 3.0 | 3.0 | 1.0 | 1.0 | 0.0 | 2.7k | 75k / 0.4k | $0.036 |
| N2  | | devkb | 1.00 | 2.0 | 2.0 | 0.0 | 0.0 | 1.0 | 0.3k | 53k / 0.1k | $0.033 |
| N3 symbol: misspelled name | | plain | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.0k | 49k / 0.1k | $0.025 |
| N3  | | devkb | 1.00 | 2.0 | 2.0 | 0.0 | 0.0 | 1.0 | 0.3k | 53k / 0.1k | $0.029 |
| N4 outline: methods of a class | | plain | 0.98 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.6k | 49k / 0.4k | $0.029 |
| N4  | | devkb | 1.00 | 2.0 | 2.0 | 0.0 | 0.0 | 1.0 | 1.7k | 54k / 0.3k | $0.058 |
| N5 uses: files with a constant | | plain | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.1k | 49k / 0.2k | $0.026 |
| N5  | | devkb | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.2k | 53k / 0.3k | $0.031 |
| N6 uses: every reference | | plain | 0.70 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 1.5k | 49k / 0.3k | $0.029 |
| N6  | | devkb | 0.71 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 1.5k | 54k / 0.3k | $0.033 |
| N7 search_docs: doc and heading | | plain | 1.00 | 3.0 | 3.0 | 2.0 | 0.0 | 0.0 | 0.1k | 74k / 0.3k | $0.034 |
| N7  | | devkb | 1.00 | 3.0 | 3.0 | 1.0 | 0.0 | 0.0 | 0.0k | 80k / 0.3k | $0.033 |
| N8 symbol glob: names by prefix | | plain | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.5k | 49k / 0.3k | $0.028 |
| N8  | | devkb | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.5k | 54k / 0.3k | $0.032 |
| **All 16 runs** | | **plain** | 0.96 | 2.4 | 2.4 | 1.1 | 0.2 | 0.0 | 1.0k | 59k / 0.3k | $0.030 |
| **All 16 runs** | | **devkb** | 0.96 | 2.1 | 2.1 | 0.5 | 0.0 | 0.5 | 0.6k | 57k / 0.2k | $0.035 |

runs using a devkb tool: 8 of 16 | by question: {'N1': 2, 'N2': 2, 'N3': 2, 'N4': 2, 'N5': 0, 'N6': 0, 'N7': 0, 'N8': 0}
tools: {'devkb:symbol': 6, 'devkb:outline': 2}

- The tools were used where they fit (N1 to N4: exact lines, a qualified method, a misspelled name, a class's methods) and not where one grep is the right tool (N5 to N8).
- The two exact-lines questions (N1, N2) returned 0.2 to 0.3k of text instead of 2.4 to 2.7k and took 2 turns instead of 3.
- The reported cost is higher for devkb ($0.030 → $0.035) because of one expensive N4 run and cold-cache writes; the steady-state cost is 11% lower.

## 2. Multi-hop exploration (8 questions, 2 repetitions)

#### Multi-hop, default configuration

| Question: callees of | Arm | Recall | Precision | F1 | Turns | Grep | File load | devkb | Cost |
|---|---|---|---|---|---|---|---|---|---|
| M1 isolation | plain | 0.75 | 0.33 | 0.46 | 4.0 | 2.0 | 1.0 | 0.0 | $0.055 |
| M1  | devkb | 1.00 | 0.30 | 0.46 | 4.0 | 0.5 | 1.0 | 1.5 | $0.056 |
| M2 open_stream | plain | 1.00 | 0.92 | 0.95 | 4.0 | 2.0 | 1.0 | 0.0 | $0.046 |
| M2  | devkb | 1.00 | 0.81 | 0.88 | 3.0 | 0.0 | 0.0 | 2.0 | $0.043 |
| M3 format_help | plain | 1.00 | 1.00 | 1.00 | 4.0 | 2.0 | 1.0 | 0.0 | $0.041 |
| M3  | devkb | 1.00 | 0.92 | 0.95 | 3.0 | 0.0 | 0.0 | 2.0 | $0.039 |
| M4 section | plain | 1.00 | 1.00 | 1.00 | 4.0 | 2.0 | 1.0 | 0.0 | $0.043 |
| M4  | devkb | 1.00 | 1.00 | 1.00 | 3.0 | 0.0 | 0.0 | 2.0 | $0.041 |
| M5 write_dl | plain | 1.00 | 0.92 | 0.95 | 3.0 | 2.0 | 0.0 | 0.0 | $0.041 |
| M5  | devkb | 1.00 | 0.86 | 0.92 | 3.0 | 0.0 | 0.0 | 2.0 | $0.040 |
| M6 handle_parse_result | plain | 1.00 | 0.84 | 0.92 | 4.0 | 2.0 | 1.0 | 0.0 | $0.071 |
| M6  | devkb | 1.00 | 1.00 | 1.00 | 3.0 | 0.0 | 0.0 | 2.0 | $0.047 |
| M7 format_progress_line | plain | 1.00 | 0.83 | 0.90 | 3.5 | 1.5 | 1.0 | 0.0 | $0.042 |
| M7  | devkb | 1.00 | 0.73 | 0.84 | 3.0 | 0.0 | 0.0 | 2.0 | $0.037 |
| M8 _pager_contextmanager | plain | 1.00 | 0.83 | 0.91 | 4.5 | 2.5 | 1.0 | 0.0 | $0.047 |
| M8  | devkb | 1.00 | 0.73 | 0.84 | 4.0 | 1.0 | 0.0 | 2.0 | $0.048 |
| **All 16 runs** | **plain** | 0.969 | 0.835 | 0.887 | 3.88 | 2.0 | 0.9 | 0.0 | $0.0482 |
| **All 16 runs** | **devkb** | 1.000 | 0.794 | 0.863 | 3.25 | 0.2 | 0.1 | 1.9 | $0.0438 |

#### Multi-hop, lean configuration

| Question: callees of | Arm | Recall | Precision | F1 | Turns | Grep | File load | devkb | Cost |
|---|---|---|---|---|---|---|---|---|---|
| M1 isolation | plain | 1.00 | 0.37 | 0.54 | 4.5 | 2.5 | 1.0 | 0.0 | $0.033 |
| M1  | devkb | 1.00 | 0.42 | 0.58 | 4.0 | 0.5 | 1.0 | 1.5 | $0.033 |
| M2 open_stream | plain | 1.00 | 1.00 | 1.00 | 4.5 | 2.0 | 1.5 | 0.0 | $0.023 |
| M2  | devkb | 1.00 | 0.92 | 0.95 | 3.0 | 0.0 | 0.0 | 2.0 | $0.021 |
| M3 format_help | plain | 1.00 | 0.77 | 0.87 | 4.0 | 2.0 | 1.0 | 0.0 | $0.018 |
| M3  | devkb | 1.00 | 1.00 | 1.00 | 3.0 | 0.0 | 0.0 | 2.0 | $0.017 |
| M4 section | plain | 1.00 | 1.00 | 1.00 | 5.0 | 3.0 | 1.0 | 0.0 | $0.019 |
| M4  | devkb | 1.00 | 1.00 | 1.00 | 3.0 | 0.0 | 0.0 | 2.0 | $0.015 |
| M5 write_dl | plain | 1.00 | 1.00 | 1.00 | 4.0 | 2.0 | 1.0 | 0.0 | $0.020 |
| M5  | devkb | 1.00 | 1.00 | 1.00 | 3.0 | 0.0 | 0.0 | 2.0 | $0.018 |
| M6 handle_parse_result | plain | 1.00 | 1.00 | 1.00 | 4.5 | 2.5 | 1.0 | 0.0 | $0.028 |
| M6  | devkb | 1.00 | 0.94 | 0.97 | 4.0 | 0.0 | 1.0 | 2.0 | $0.028 |
| M7 format_progress_line | plain | 1.00 | 0.67 | 0.80 | 4.0 | 1.5 | 1.5 | 0.0 | $0.019 |
| M7  | devkb | 1.00 | 0.67 | 0.80 | 3.0 | 0.0 | 0.0 | 2.0 | $0.016 |
| M8 _pager_contextmanager | plain | 1.00 | 0.77 | 0.87 | 5.0 | 3.0 | 1.0 | 0.0 | $0.030 |
| M8  | devkb | 1.00 | 0.83 | 0.91 | 4.0 | 1.0 | 0.0 | 2.0 | $0.040 |
| **All 16 runs** | **plain** | 1.000 | 0.823 | 0.885 | 4.44 | 2.3 | 1.1 | 0.0 | $0.0237 |
| **All 16 runs** | **devkb** | 1.000 | 0.847 | 0.902 | 3.38 | 0.2 | 0.2 | 1.9 | $0.0236 |


Reading the tables:
- **Grep fell from 2.0 to 0.2 calls per run and whole-file reads from 0.9 to 0.1**; `symbol` was called 1.9 times per run: once for the function, then once for all its callees (30 of the 62 calls named several functions, comma-separated).
- **Recall:** devkb gave every callee's first line in every run. Plain gave a constructor's line instead of the class's first line for three classes in M1 (both repetitions), which the scorer counts as name-only (0.969); `symbol` returns the class's own range.
- **Cost is dominated by the fixed prompt**, not by the tool results: the prompt is 24k tokens in the default configuration (7k with built-ins restricted), written to the cache once and re-read on every call; the tool results of a whole run add about 2k. Removing 2 greps and 0.8 reads saves under $0.001; removing a turn saves about $0.003.

## 3. Why turns, and then cost, moved

1. **Before:** 15 of 16 devkb runs began with a `ToolSearch` call (Claude Code defers MCP tools), so `symbol` replaced a grep but one turn was added: 4.19 turns against plain's 4.12, and cost $0.0474 against $0.0456.
2. **The fix:** `symbol`, `outline` and `pack` carry `_meta {"anthropic/alwaysLoad": true}` (#46). They load with the prompt, the other tools stay deferred. A skill cannot control this and a plugin cannot set `ENABLE_TOOL_SEARCH`; setting it to `false` also loads Claude Code's own deferred built-ins (+18k tokens).
3. **Then:** the multi-hop turns fell to 3.25 (-22% against the earlier deferred arm) and cost to $0.0438 against plain's $0.0482. The same pairs, rerun on the current code with new repetitions, are the "default" rows above.

## 4. Scoring corrections

Two scorer flaws made earlier tables of this document wrong; both are fixed in `bench/readtools/` and every number above is rescored.
- **Multi-hop precision** counted as wrong any repository-defined name outside a truth list that omitted callees whose name several classes share (`consume_value`, `process_value`, `get_parameter_source`), class qualifiers and prose words. The first version showed a score drop of about 0.02 for devkb; with the corrected truth the paired difference is -0.003 [-0.036, +0.032] on the earlier runs and the intervals above on these.
- **N6 ("every reference")** read only the first line number after each file name, so `core.py: 45, 1561` earned half credit. It now attributes every number on a line to the file name before it. N6 scores 0.70 and 0.71; the remaining gap is references the agents did not list.

## 5. Earlier measurements that still hold

- **Speed on Zephyr** (147,307 symbols, 15,912 C/C++ files): first call 1.5 s while the name tables load, then 30 to 500 ms for `symbol`, 30 ms for `outline`, 0.8 to 1.5 s for `uses` over 70,000 files, 0.3 s for `search_docs`. As command-line calls (graph loaded each time): 1.6 to 4 s; see `performance-v0.2.6-to-main.md`.
- **Feature builds** (two runs adding C/C++ support, with the tools connected and the instruction loaded): 0 calls to any read tool. Of 63 greps, 34% searched external reference checkouts outside any graph, 23% were free-text patterns, 6% were outlines and none was a definition or caller lookup; agents read known files with offsets. A feature build is not a navigation task. (Run on earlier code; not repeated.)

## 6. Conclusion

The read tools are fast and accurate (exact ranges, typo tolerance, qualified names, an honest "end unknown" for TypeScript), agents use them for definition lookups, and since the first-lookup tools load with the prompt they remove a turn instead of adding one: **about 12 to 24% fewer turns and about 10% lower steady-state cost, with no measurable change in correctness.** One-shot cost is flat to slightly lower on multi-hop questions and not lower on single-lookup ones.
They do not help where one grep already answers (N5 to N8) or where the task is writing code in a repository rather than finding things in it.

Open:
1. Multi-hop precision is lower in the default configuration; look at what a `symbol` reply invites the agent to add.
2. A larger repository and harder questions (a behaviour spread across many files), where grep returns far more text than a range does.
3. The prompt cost: the 12-tool `lean-pack` set adds 2 to 3k tokens against plain; the `nav` set (`symbol`, `outline`, `pack`) is about 2k.
4. A hook that offers the tool just before a definition grep would help questions that one grep answers.
