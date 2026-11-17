# What are the agents grepping for, and can the graph answer it?

2026-11-16. Method: every grep in the nine feature-build runs (plain, devkb, devkb + specification, SPEC-DKB-002): 275 grep events, 60k tokens of text returned. Each event is classified by rules in `bench/exercises/cpp/grep_purposes.py`
(`python3 grep_purposes.py EVAL_DIR GRAPH_NODES.jsonl --markdown OUT`), then checked on about 45 random samples; the rules misfile a few percent of events (mostly regexes that mix a definition lookup with a text search).
Cost = text returned, weighted by the model calls still to come, because text stays in the context and is paid for again on every later call. Heredoc bodies are removed, and a command that chains several
operations has its output split across them.

## Result

| Kind of grep | What the agent is trying to learn | Events | Text returned | Share of grep cost | Cumulative | Can the graph answer it? | What would answer it |
|---|---|---|---|---|---|---|---|
| filter the output of another command | trim the output of tests, git or a file read down to the lines it cares about | 49 (17%) | 14.5k | 30.1% | 30% | not a search | nothing: grep is a filter here, not a search |
| find where one symbol is defined | read a function or class: 90% add -A/-B/-C, i.e. they want the body, not the location | 31 (11%) | 8.2k | 14.7% | 45% | yes, data exists | a `symbol(name)` call returning signature, file and exact line range, with the source on request (the graph stores line_start and line_end) |
| outline: list the definitions and imports in a file | see the shape of a file before reading or editing it | 20 (7%) | 8.2k | 11.9% | 57% | yes, data exists | an `outline(file)` call: Symbols of the file with line ranges (the graph has them; `explain_area` shows only key symbols) |
| find the callers or users of a function or class the graph knows | who uses this function (impact of a change) | 16 (5%) | 6.4k | 11.7% | 68% | yes, today | `callers`, `pack(refactor)`: available now; the instruction tells agents to grep one-hop lookups |
| find text in docs, specs and tickets | check what the README, scope or spec says | 32 (11%) | 7.1k | 9.6% | 78% | partly | `find_docs` ranks specs/ADRs by topic; the text inside docs is not indexed |
| find uses of a module, key or name the graph has no node for | where is this module, import, key or argument name used | 48 (17%) | 4.9k | 7.9% | 86% | no, needs new data | new graph data: modules and imports as nodes with USES edges |
| find a string, phrase or pattern in code | locate code by an idiom or literal | 32 (11%) | 4.4k | 6.1% | 92% | partly | only error messages and env vars are indexed (ErrorSignature, ConfigKey) |
| find tests | which tests touch this | 15 (5%) | 2.6k | 3.5% | 96% | yes, today | `tests_for`, `tests_to_run`: available now |
| find uses of a constant or macro | where is this module-level constant or macro used | 8 (2%) | 2.3k | 3.3% | 99% | no, needs new data | new graph data: module-level constants and macros as nodes |
| search an external repository or a scratch file (no graph) | read the reference corpus or a temporary file | 13 (4%) | 1.2k | 0.9% | 100% | no, outside the graph | nothing: they are outside the repository being edited |
| count or check that something is present | verify an edit or a count | 11 (4%) | 0.2k | 0.1% | 100% | not a search | nothing: verification, not search |

**Reading the cost.** The cost is flatter than 80/20: it takes 6 of 11 kinds to reach 80% of grep cost. Two of the eleven kinds
(definition lookup and outline) are 27% of all grep cost (38% of the cost of real searches), and the four kinds the graph can already answer
from data it holds (adding callers and tests) are 42% (60% of searches). The 20% to pick is therefore the **definition and outline** pair: one need ("show me the code
structure and a symbol's body, with exact lines") and no schema change.

Cost here = text returned to the model, weighted by the model calls still to come (text stays in context). Events = 275 greps in 9 build runs.

## What the purposes are, in the agents' own commands

1. **"Where is this defined" is really "show me this function"**: 28 of 31 definition greps add `-A`, `-B` or `-C` and read the lines after the match (`grep -n "def _tests_of" -A25 devkb/process_api.py`).
   The graph stores the exact range of all 1,020 Symbols (`line_start`, `line_end`), while the agents guess the length: the median function is 8 lines, so a fixed `-A25` over-reads 87% of functions and cuts 11% short.
2. **Outline is navigation before an edit**: `grep -n "^def \|^class " file.py | head`. The graph holds the same list with line ranges.
3. **Callers are the one need devkb already serves**, and the instruction tells agents to grep one-hop lookups. In the chain questions the same need is the main grep: the plain arm made 84 greps (41 of them caller lookups, 27k tokens of text),
   the devkb arm 38 greps (24 caller lookups, 9.8k tokens).
4. **A quarter of the cost is not searching at all**: grep as a filter on test output, git output, or a `cat file | grep` (11 events, 9.4k of the 14.5k tokens: reading part of a file).
5. **11% of the cost looks up things that are not nodes**: modules and imports (`cpp_symbols`, `framework`), module-level constants (`_PY_TEST`, `_JS_TEST`). The graph has only function, class and method Symbols.

## Which 20% to pick

The cost is flatter than 80/20 (6 of 11 kinds reach 80%). The best 20% is the **definition + outline pair: 27% of all grep cost (38% of the cost of real searches)**, a single need ("show me the structure and the body of this thing, with exact lines")
that the graph can answer from data it already holds. Adding callers and tests (already available) the graph covers 42% of the cost (60% of real searches). Nothing else is cheap to add:
docs and phrase search are only partly indexed, modules and constants need new nodes (11% of the cost), and 30% is not a search.

Proposed, in this order:
1. `outline(file)`: the Symbols of a file, kind and line range, optionally with docstring summaries (data exists; no schema change).
2. `symbol(name)`: signature, file and exact range, with the source of the range on request, bounded by the graph's own `line_end` instead of a guessed `-A25` (data exists; no schema change).
3. Put both in the default `lean-pack` toolset and add one line to the instruction ("to read a function, ask `symbol`, not grep -A").
4. Later, if wanted: modules, imports and module-level constants as nodes (needs schema, ADR-gated), 11% of the cost.

Not measured: whether agents would call the new tools (in four earlier rounds they ignored extra tools; the chain questions show they do use devkb when the tool matches the question), and the token saving. The first needs a rerun of a build with the tools added;
the second can be estimated from the 31 definition greps (8.2k tokens) and 20 outlines (8.2k tokens): up to 27% of grep text is the ceiling.
