# Read tools: what the benchmarks show (2026-11-16)

Tools under test: `symbol`, `outline`, `uses`, `search_docs` (SPEC-DKB-003). Model: Sonnet in every arm. Small samples; directional.

## 1. Zephyr scale: the tools are fast

First call 1.5 s (name tables), then 30 to 500 ms for `symbol`, 30 ms for `outline`, 0.8 to 1.5 s for `uses` over 70,000 files, 0.3 s for `search_docs`
(147,307 symbols, 15,912 C/C++ files).

## 2. Feature builds (adding C/C++ support, 2 runs with the tools): not used

The tools were connected (preflight: server connected, a real `symbol` call returned) and the instruction naming them reached the agent (it quoted the section when asked).
**Both builds made 0 calls to `symbol`, `outline`, `uses` or `search_docs`.** They made 26 and 30 greps, cost $3.43 and $2.68 (earlier devkb arms: $1.78 to $2.69).

Why: the greps in these two builds were not definition or caller lookups. Of 63 greps, 34% searched the external reference checkouts (outside any graph), 23% were free-text patterns, 6% were outlines,
**0% were definition lookups, 0% caller lookups**. The agents read known files with the `Read` tool and offsets. A feature build that writes a new module and inspects outside corpora is not a navigation task,
and the earlier nine-run analysis (3.4 definition greps per run) does not hold for every task.

## 3. Navigation questions (8 questions about click, 2 repetitions, plain against devkb with the read tools)

Answers are scored against exact truth from the source (line numbers from the parser, file sets from git, method lists from the AST).

| Question | Tool it exercises | Arm | Score | Turns | Model calls | Grep | File load | devkb | Text returned | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| N1 symbol: exact lines of a function | | plain | 1.00 | 3.0 | 3.0 | 1.0 | 1.0 | 0.0 | 2.4k | 74k / 0.4k | $0.035 |
| N1  | | devkb | 1.00 | 3.0 | 3.0 | 0.0 | 0.0 | 1.0 | 0.2k | 79k / 0.2k | $0.033 |
| N2 symbol: qualified method lines | | plain | 1.00 | 3.0 | 3.0 | 1.0 | 1.0 | 0.0 | 2.7k | 75k / 0.4k | $0.036 |
| N2  | | devkb | 1.00 | 3.0 | 3.0 | 0.5 | 0.5 | 0.5 | 1.5k | 79k / 0.3k | $0.036 |
| N3 symbol: misspelled name | | plain | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.0k | 49k / 0.1k | $0.006 |
| N3  | | devkb | 1.00 | 3.0 | 3.0 | 0.0 | 0.0 | 1.0 | 0.3k | 79k / 0.2k | $0.010 |
| N4 outline: methods of a class | | plain | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.6k | 49k / 0.4k | $0.010 |
| N4  | | devkb | 1.00 | 3.0 | 3.0 | 0.0 | 0.0 | 1.0 | 1.8k | 79k / 0.4k | $0.016 |
| N5 uses: files with a constant | | plain | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.1k | 49k / 0.2k | $0.008 |
| N5  | | devkb | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.1k | 52k / 0.2k | $0.008 |
| N6 uses: every reference | | plain | 0.82 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 1.5k | 49k / 0.5k | $0.013 |
| N6  | | devkb | 0.66 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 1.5k | 52k / 0.4k | $0.012 |
| N7 search_docs: doc and heading | | plain | 1.00 | 2.5 | 2.5 | 1.5 | 0.0 | 0.0 | 0.1k | 61k / 0.3k | $0.010 |
| N7  | | devkb | 1.00 | 3.0 | 3.0 | 1.0 | 0.0 | 0.0 | 0.0k | 78k / 0.2k | $0.011 |
| N8 symbol glob: names by prefix | | plain | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.5k | 49k / 0.3k | $0.009 |
| N8  | | devkb | 1.00 | 2.0 | 2.0 | 1.0 | 0.0 | 0.0 | 0.5k | 52k / 0.3k | $0.009 |
| **All 16 runs** | | **plain** | 0.98 | 2.3 | 2.3 | 1.1 | 0.2 | 0.0 | 1.0k | 57k / 0.3k | $0.016 |
| **All 16 runs** | | **devkb** | 0.96 | 2.6 | 2.6 | 0.6 | 0.1 | 0.4 | 0.7k | 69k / 0.3k | $0.017 |

runs using a devkb tool: 7 of 16 | by question: {'N1': 2, 'N2': 1, 'N3': 2, 'N4': 2, 'N5': 0, 'N6': 0, 'N7': 0, 'N8': 0}
tools: {'devkb:symbol': 5, 'devkb:outline': 2}


## 4. What it says

- **Adoption follows the question.** Where the question is "exact lines of X", "a misspelled name" or "the methods of this class", the agent used `symbol` or `outline` in 7 of 8 runs
  (and in 0 of 8 runs for "files with this constant", "every reference", "which doc", "names by prefix", where one grep is already the right tool). `uses` and `search_docs` were never chosen.
- **Same correctness, same cost.** Scores are 0.98 and 0.96; cost per question $0.016 and $0.017. These questions take plain 2.3 turns and one grep, so there is little to save.
- **Where it does save is text.** The definition question returned 0.2k of text instead of 2.4k (a `grep -A` plus a read), the pattern the grep analysis predicted; but a tool call is one more turn than a grep on a two-turn question, and
  the larger tool list adds about 1.5k tokens of context per model call (+21% context here). The two effects cancel.
- **Tool definitions are a standing cost.** 12 tools at about 1.5k tokens per call; trimming descriptions or the default toolset is the lever if the tools do not pay for themselves on the tasks a team runs.

## 5. Conclusion for the owner

The tools are fast, correct and accurate (exact ranges, typos, qualified names, honest `end unknown` for TypeScript) and agents use them when the question matches. They did not lower cost or raise accuracy on easy navigation
and were not used in a feature build, so **their value is not yet shown**. The case they were built for, multi-step exploration of unfamiliar code (several lookups before an answer), is untested; the chain benchmark (callers at any depth)
is where devkb already saves 37%.

Next steps, in order of expected value:
1. A multi-hop exploration benchmark (find where a behaviour lives, then every function it calls, with line ranges), 10 or more questions, on two repositories.
2. Batch lookups in one call (`symbol` with several names): grep batches alternatives in one command, so one lookup per call loses a turn.
3. Trim the standing cost: shorter tool descriptions; consider `outline` and `symbol` only in the default set.
4. For adoption beyond the model's own choice, a hook that offers the tool when a grep for a definition is about to run.
