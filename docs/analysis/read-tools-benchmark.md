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


## 4. Multi-hop exploration (8 questions about click, 2 repetitions, plain against devkb with the read tools)

"Find the function F; list every function it calls directly that is defined in `src/click/`, each with its file and first line": one lookup of F and one per callee (4 to 6 callees).
Truth from the AST (calls written `name()` or `self.name()`, builtins excluded). Score: callee found with its first line = 1, name only = 0.5, then F1 against the repository-defined names the answer lists wrongly.

| Question: callees of | | Arm | Score | Turns | Model calls | Grep | File load | devkb | Text returned | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 isolation | | plain | 0.63 | 5.0 | 4.0 | 2.5 | 1.5 | 0.0 | 9.1k | 105k / 1.1k | $0.058 |
| M1  | | devkb | 0.63 | 5.0 | 4.0 | 0.5 | 1.0 | 1.5 | 10.5k | 112k / 0.9k | $0.060 |
| M2 open_stream | | plain | 1.00 | 4.5 | 4.0 | 2.0 | 1.5 | 0.0 | 4.0k | 101k / 0.9k | $0.047 |
| M2  | | devkb | 0.96 | 4.0 | 4.0 | 1.0 | 0.0 | 1.0 | 4.4k | 108k / 0.7k | $0.048 |
| M3 format_help | | plain | 0.84 | 4.0 | 4.0 | 2.0 | 1.0 | 0.0 | 1.9k | 100k / 0.7k | $0.041 |
| M3  | | devkb | 0.80 | 4.0 | 4.0 | 0.5 | 0.0 | 1.5 | 2.2k | 106k / 0.5k | $0.042 |
| M4 section | | plain | 0.89 | 4.5 | 4.0 | 2.5 | 1.0 | 0.0 | 1.5k | 100k / 0.7k | $0.041 |
| M4  | | devkb | 0.89 | 4.0 | 4.0 | 0.5 | 0.0 | 1.5 | 1.4k | 106k / 0.4k | $0.040 |
| M5 write_dl | | plain | 0.80 | 4.0 | 4.0 | 2.0 | 1.0 | 0.0 | 3.7k | 101k / 0.8k | $0.044 |
| M5  | | devkb | 0.80 | 4.0 | 4.0 | 0.5 | 0.0 | 1.5 | 3.2k | 107k / 0.5k | $0.044 |
| M6 handle_parse_result | | plain | 0.52 | 4.0 | 4.0 | 2.0 | 1.0 | 0.0 | 6.0k | 103k / 1.0k | $0.050 |
| M6  | | devkb | 0.49 | 4.0 | 4.0 | 1.0 | 0.0 | 1.0 | 5.8k | 109k / 0.8k | $0.051 |
| M7 format_progress_line | | plain | 0.80 | 3.0 | 3.0 | 1.0 | 1.0 | 0.0 | 3.9k | 75k / 0.5k | $0.038 |
| M7  | | devkb | 0.81 | 3.5 | 3.5 | 0.5 | 0.5 | 1.0 | 3.0k | 93k / 0.5k | $0.042 |
| M8 _pager_contextmanager | | plain | 0.70 | 4.0 | 3.0 | 2.0 | 1.0 | 0.0 | 3.8k | 77k / 0.9k | $0.045 |
| M8  | | devkb | 0.73 | 5.0 | 5.0 | 2.0 | 0.0 | 1.0 | 3.6k | 136k / 0.8k | $0.053 |
| **All 16 runs** | | **plain** | 0.77 | 4.1 | 3.8 | 2.0 | 1.1 | 0.0 | 4.2k | 95k / 0.8k | $0.046 |
| **All 16 runs** | | **devkb** | 0.76 | 4.2 | 4.1 | 0.8 | 0.2 | 1.2 | 4.3k | 110k / 0.6k | $0.047 |

runs using a devkb tool: 15 of 16 | by question: {'M1': 2, 'M2': 2, 'M3': 2, 'M4': 2, 'M5': 2, 'M6': 2, 'M7': 1, 'M8': 2}
tools: {'devkb:symbol': 20}


**Adoption is near-total when the work is definition lookups: `symbol` in 15 of 16 runs (20 calls), `outline`, `uses` and `search_docs` not needed.** Grep fell from 2.0 to 0.8 calls per run and whole-file reads from 1.1 to 0.2 (the spec's target of at least 60% fewer
definition and outline greps is met here). Correctness (0.77 and 0.76), turns (4.1 and 4.2) and cost ($0.046 and $0.047) did not change: a `symbol` call takes the same turn a grep did, a plain agent batches
several names into one grep, and the tool list adds about 15k tokens of context over a run (+16%).

## 5b. Why cost did not fall, and the fix tested (multi-hop, 16 runs per arm)

Cost per run is mostly a fixed prompt (about 24k tokens in the default Claude Code configuration), which is written to the cache once and re-read on every call; fewer greps and reads cannot move it (`cost_breakdown.py`: prefix write 47-50%, history re-read 17-19%, new tool results 19-24%, output 7%).
Turns did not fall because deferred MCP tools need a `ToolSearch` call first (15 of 16 devkb runs): one turn spent to save one turn.

Turning tool search off reloads Claude Code's own deferred built-ins too (+18k tokens), so a fair test restricts built-ins in both arms (`--tools Read,Grep,Glob,Bash`, tool search off) and gives devkb only `symbol`, `outline`, `pack` (toolset `nav`; `symbol` also takes comma-separated names):

| Arm | Score | Turns | Model calls | First-call context | Cost per run |
|---|---|---|---|---|---|
| plain, default configuration | 0.772 | 4.12 | 3.75 | 24.3k | $0.0456 |
| plain, 4 built-ins, tool search off | 0.765 | 4.25 | 3.88 | 7.3k | $0.0241 |
| nav (3 devkb tools), same | 0.747 | **3.31** | **3.06** | 9.3k | $0.0286 |

Turns and model calls fall 21-22% (symbol 1.9 calls per run, grep 2.1 to 0.1, reads 1.1 to 0.25). Cost is 19% higher in these one-shot runs, because every run writes its cache prefix cold (nav writes 3.2k tokens of prefix against 0.8k) and its `symbol` replies are larger than grep output (475 tokens on average, source requested in half the calls). Score is within noise (0.747 and 0.765).
Restricting the built-in tool set alone, with no devkb, cut cost 47%.

## 5. What it says

- **Adoption follows the question.** Where the question is "exact lines of X", "a misspelled name" or "the methods of this class", the agent used `symbol` or `outline` in 7 of 8 runs
  (and in 0 of 8 runs for "files with this constant", "every reference", "which doc", "names by prefix", where one grep is already the right tool). `uses` and `search_docs` were never chosen.
- **Same correctness, same cost (here and in section 4).** Scores are 0.98 and 0.96; cost per question $0.016 and $0.017. These questions take plain 2.3 turns and one grep, so there is little to save.
- **Where it does save is text.** The definition question returned 0.2k of text instead of 2.4k (a `grep -A` plus a read), the pattern the grep analysis predicted; but a tool call is one more turn than a grep on a two-turn question, and
  the larger tool list adds about 1.5k tokens of context per model call (+21% context here). The two effects cancel.
- **Tool definitions are a standing cost.** 12 tools at about 1.5k tokens per call; trimming descriptions or the default toolset is the lever if the tools do not pay for themselves on the tasks a team runs.

## 6. Conclusion for the owner

The tools are fast, correct and accurate (exact ranges, typos, qualified names, honest `end unknown` for TypeScript) and agents use them when the question matches. They did not lower cost or raise accuracy on easy navigation
and were not used in a feature build, so **their value is not yet shown**. The multi-step case (section 4) shows agents switching from grep to `symbol` almost completely, with no change in correctness, turns or cost; the chain benchmark (callers at any depth) is where devkb already saves 37%.

Next steps, in order of expected value:
1. Batch lookups in one call (`symbol` with several names): plain agents batch alternatives into one grep, so one lookup per call is where the saving is lost (4 to 6 lookups per multi-hop question).
2. A larger repository and harder questions (a behaviour spread over many files), where grep returns far more text than a range does.
3. Trim the standing cost: shorter tool descriptions; consider `outline` and `symbol` only in the default set.
4. For adoption beyond the model's own choice, a hook that offers the tool when a grep for a definition is about to run.
