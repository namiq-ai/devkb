# Does devkb help an agent on C and C++? Chain questions, scored against the compiler

2026-11-16. Exploratory: 5 questions, 2 repositories, 2 repetitions per arm (20 runs), one model (Sonnet), one session.

## Setup

- **Question** (read-only): "List every production function that can reach `F`, directly or indirectly, and the test files that exercise it."
- **Truth**: libclang call graph, text-visible edges only (calls produced by macro expansion are excluded: a text scan cannot see them), production code only. Sizes: leveldb `TableBuilder::WriteRawBlock` 24 callers, `VersionSet::LogAndApply` 8, `Footer::DecodeFrom` 35; cJSON `print_value` 9, `cJSON_Delete` 48.
- **Arms**: `plain` (grep, read, find) and `devkb` (the same tools plus the MCP server in `lean-pack` mode and the `AGENTS.md` block `devkb init` writes), graph built by the C/C++ code of PR #35. devkb was proven connected before the runs.
- **Scoring**: function names in backticks, matched to the truth by short name. Recall is solid; precision is approximate, because an agent that also lists a real caller the text-visible truth excludes is counted wrong.

## Result

| Question | Arm | Truth | Listed | Precision | Recall | Test files | Turns | Model calls | Cost | Grep | File load | devkb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| leveldb `WriteRawBlock` | plain | 24 | 48 | 0.51 | 1.00 | 0.62 | 7.5 | 6.5 | $0.125 | 6.0 (14.9k) | 0 | 0 |
|  | devkb | 24 | 22 | 0.94 | 0.88 | 0.50 | 4.0 | 4.0 | $0.064 | 1.0 (0.8k) | 0 | 1.0 (4.9k) |
| leveldb `LogAndApply` | plain | 8 | 40 | 0.20 | 1.00 | 1.00 | 9.0 | 6.5 | $0.121 | 7.0 (10.7k) | 0.5 (1.4k) | 0 |
|  | devkb | 8 | 23 | 0.33 | 0.94 | 0.75 | 7.0 | 6.5 | $0.103 | 4.0 (9.2k) | 0 | 1.0 (1.4k) |
| leveldb `Footer::DecodeFrom` | plain | 35 | 57 | 0.61 | 0.99 | 0.60 | 12.5 | 9.0 | $0.229 | 10.0 (33.8k) | 1.0 (4.0k) | 0 |
|  | devkb | 35 | 47 | 0.67 | 0.90 | 0.40 | 20.5 | 13.5 | $0.179 | 10.0 (14.4k) | 1.0 (1.6k) | 6.5 (2.8k) |
| cJSON `print_value` | plain | 9 | 8 | 0.94 | 0.78 | 0.70 | 3.5 | 3.5 | $0.053 | 2.5 (3.1k) | 0 | 0 |
|  | devkb | 9 | 10 | 0.86 | 1.00 | 0.90 | 3.5 | 3.5 | $0.051 | 0.5 (0.1k) | 0 | 1.0 (3.2k) |
| cJSON `cJSON_Delete` | plain | 48 | 48 | 0.97 | 0.96 | 0.87 | 10.0 | 7.5 | $0.180 | 8.0 (29.5k) | 0 | 0 |
|  | devkb | 48 | 47 | 0.99 | 0.97 | 0.84 | 8.0 | 8.0 | $0.107 | 2.0 (3.6k) | 1.0 (0.3k) | 2.0 (9.2k) |
| **All 10 runs** | **plain** | | | 0.64 | 0.94 | 0.76 | 8.5 | 6.6 | $0.141 | 6.7 (18.4k) | 0.3 (1.1k) | 0 |
| **All 10 runs** | **devkb** | | | 0.76 | 0.94 | 0.68 | 8.6 | 7.1 | $0.101 | 3.5 (5.6k) | 0.4 (0.4k) | 2.3 (4.3k) |

Calls per run (mean of two); parentheses give the text returned to the model. Grep = the Grep tool or a shell grep, file load = Read or shell cat/sed/head. Truth is the number of production callers the compiler finds; Listed is how many functions the agent named.

Per run (turns, model calls and cost for every run):

| Repo | Question | Arm | Run | Turns | Model calls | Cost |
|---|---|---|---|---|---|---|
| leveldb | WriteRawBlock | plain | r1 | 10 | 8 | $0.176 |
| leveldb | WriteRawBlock | plain | r2 | 5 | 5 | $0.073 |
| leveldb | WriteRawBlock | devkb | r1 | 3 | 3 | $0.077 |
| leveldb | WriteRawBlock | devkb | r2 | 5 | 5 | $0.051 |
| leveldb | LogAndApply | plain | r1 | 5 | 5 | $0.116 |
| leveldb | LogAndApply | plain | r2 | 13 | 8 | $0.125 |
| leveldb | LogAndApply | devkb | r1 | 6 | 6 | $0.129 |
| leveldb | LogAndApply | devkb | r2 | 8 | 7 | $0.076 |
| leveldb | DecodeFrom | plain | r1 | 10 | 8 | $0.221 |
| leveldb | DecodeFrom | plain | r2 | 15 | 10 | $0.237 |
| leveldb | DecodeFrom | devkb | r1 | 24 | 16 | $0.216 |
| leveldb | DecodeFrom | devkb | r2 | 17 | 11 | $0.141 |
| cJSON | print_value | plain | r1 | 4 | 4 | $0.080 |
| cJSON | print_value | plain | r2 | 3 | 3 | $0.026 |
| cJSON | print_value | devkb | r1 | 3 | 3 | $0.072 |
| cJSON | print_value | devkb | r2 | 4 | 4 | $0.030 |
| cJSON | cJSON_Delete | plain | r1 | 10 | 8 | $0.209 |
| cJSON | cJSON_Delete | plain | r2 | 10 | 7 | $0.150 |
| cJSON | cJSON_Delete | devkb | r1 | 7 | 7 | $0.119 |
| cJSON | cJSON_Delete | devkb | r2 | 9 | 9 | $0.096 |

All 10 plain runs against all 10 devkb runs:

| | plain | devkb |
|---|---|---|
| Median cost | $0.138 | **$0.087 (-37%)** |
| Mean cost | $0.141 | $0.101 (-28%) |
| Recall | 0.94 | 0.94 |
| Precision | 0.64 | **0.76** |
| F1 | 0.71 | **0.81** |
| Mean turns | 8.5 | 8.6 |
| Mean model calls | 6.6 | 7.1 |
| Runs that called devkb | n/a | **10 of 10** |

## What it says

- **devkb works when the question is a chain.** Every devkb run called it (2.3 calls on average), it was cheaper on 4 of 5 questions and equal on the fifth, and the lists were tighter (fewer names that are not callers). This matches the project's published Python result (`lean-pack`: 53% cheaper, quality +0.057, 100 of 100 runs called `pack`).
- **Recall is the same**, so the saving is not bought with missed callers.
- **Test files are the weak spot**: devkb found fewer of them on 3 of 5 questions (mean 0.68 against 0.76). Tests that reach the function through fixtures and test macros (`TEST_F`) are what a text graph misses and grep catches.
- **One anomaly**: on `Footer::DecodeFrom` the devkb arm made 6.5 calls and 20 turns (plain: 12), because the pack was Incomplete and the agent kept checking. It was still 22% cheaper.
- **Earlier C++ feature builds** (exercises 4 to 6) gave devkb no measurable benefit because they were the wrong kind of task: agents read and patch code, and a pack of callers barely matters.

## Limits

20 runs, five questions, two repositories, text-visible truth only, one model, one session; the precision numbers move with how the agent words its answer. Directional, not a result.

## What the agents did: grep calls, file loads, devkb calls (mean per run, calls and text returned to the model)

`bench/exercises/cpp/tool_usage.py` classifies every tool call in the transcripts: `grep` (the Grep tool or a shell grep), `file load` (the Read tool or shell cat/sed/head), `devkb` (an MCP call or a `devkb` command), `find/list`.

| Repository | Arm | grep | file load | devkb | find/list | Total calls | Text returned |
|---|---|---|---|---|---|---|---|
| cJSON (4 runs) | plain | 5.2 calls (16.3k) | 0.0 | 0.0 | 0.0 | 5.8 | 16.4k |
| | devkb | 1.2 (1.9k) | 0.5 (0.1k) | 1.5 (6.2k) | 0.0 | 4.8 | 8.2k |
| leveldb (6 runs) | plain | 7.7 (19.8k) | 0.5 (1.8k) | 0.0 | 0.5 (0.2k) | 8.7 | 21.8k |
| | devkb | 5.0 (8.2k) | 0.3 (0.5k) | 2.8 (3.1k) | 0.2 (0.1k) | 9.5 | 11.9k |
| All 10 runs | plain | 6.7 (18.4k) | 0.3 (1.1k) | 0.0 | 0.3 | 7.5 | 19.7k |
| | devkb | 3.5 (5.6k) | 0.4 (0.4k) | 2.3 (4.3k) | 0.1 | 7.6 | 10.5k |

Per question (mean of two runs; calls, text returned):

| Question | Arm | grep | file load | devkb |
|---|---|---|---|---|
| cJSON `cJSON_Delete` | plain | 8.0 (29.5k) | 0 | 0 |
| | devkb | 2.0 (3.6k) | 1.0 (0.3k) | 2.0 (9.2k) |
| cJSON `print_value` | plain | 2.5 (3.1k) | 0 | 0 |
| | devkb | 0.5 (0.1k) | 0 | 1.0 (3.2k) |
| leveldb `DecodeFrom` | plain | 10.0 (33.8k) | 1.0 (4.0k) | 0 |
| | devkb | 10.0 (14.4k) | 1.0 (1.6k) | 6.5 (2.8k) |
| leveldb `LogAndApply` | plain | 7.0 (10.7k) | 0.5 (1.4k) | 0 |
| | devkb | 4.0 (9.2k) | 0 | 1.0 (1.4k) |
| leveldb `WriteRawBlock` | plain | 6.0 (14.9k) | 0 | 0 |
| | devkb | 1.0 (0.8k) | 0 | 1.0 (4.9k) |

Reading: the number of tool calls is the same (7.5 and 7.6); what changes is **which** tool. devkb replaces about half of the grep calls with one or two pack calls, and the agent reads about half as much text (10.5k against 19.7k). Agents almost never load whole files in either arm (0.3 to 0.5 per run): they grep. One pack call returns 1.4k to 9.2k, a grep 0.8k to 4k; the saving is in not running six to eight greps and reading their output. Leveldb `DecodeFrom` is the exception: one devkb run made 11 pack/devkb calls (4.8k returned) and 8 greps, because the pack said Incomplete.

## Turns and model calls

`turns` is the run's reported `num_turns` (one per model response including tool-result round trips); `model calls` counts distinct model responses.

| Repository | Arm | Turns (mean) | Model calls (mean) | Cost (mean) |
|---|---|---|---|---|
| cJSON (4 runs) | plain | 6.8 | 5.5 | $0.116 |
| | devkb | 5.8 | 5.8 | $0.079 |
| leveldb (6 runs) | plain | 9.7 | 7.3 | $0.158 |
| | devkb | 10.5 | 8.0 | $0.115 |
| All 10 runs | plain | 8.5 (median 10.0, range 3-15) | 6.6 | $0.141 |
| | devkb | 8.6 (median 6.5, range 3-24) | 7.1 | $0.101 |

Per question (mean of two runs): cJSON `cJSON_Delete` plain 10.0 / devkb 8.0; cJSON `print_value` 3.5 / 3.5; leveldb `WriteRawBlock` 7.5 / 4.0; `LogAndApply` 9.0 / 7.0; `Footer::DecodeFrom` 12.5 / 20.5.

Reading: the means are equal (8.5 and 8.6); the median is lower with devkb (6.5 against 10.0) because most questions finish in 3 to 8 turns, and one question, `DecodeFrom`, pulls the devkb mean up (17 and 24 turns, an Incomplete pack the agent kept checking). Cost is lower even there, because a pack turn adds less context than a grep turn.
