# No devkb, devkb over MCP, devkb over the CLI: everything measured (2026-11-17)

Question: how should an agent be given devkb, if at all? Over the MCP server (tool definitions in the prompt), over
the command line (`devkb symbol|outline|uses|docs|pack` from the shell), or not at all? This page puts every
measurement taken so far side by side. A cell says "not measured" where no run exists; nothing is extrapolated. All
runs use Sonnet. Most cells rest on 2 runs per case: read differences under about 30% in cost, or one fix in six, as
noise (the same setup on the same ticket varied by 1.5–2× in cost between two runs, §2.4).

## 1. The answer by task type

| Task | No devkb | devkb over MCP | devkb over the CLI | Verdict |
|---|---|---|---|---|
| **Small bug fixes** (ticket names the file) | baseline | used in 8 of 84 runs; cost −11% to +17% (5 tests); hook +4% to +30% | 0 navigation calls in 6 runs; cost −16% (noise) | devkb is not used; CLI costs nothing extra, MCP costs its tool definitions |
| **Fixes to devkb itself, with the repository policy** (#126) | $0.333, 3/6 fixed | $0.416 (+25%), 2/6; revised: $0.366 (+10%), 4/6 | **$0.281**, 3/6 | CLI-only is the cheapest way to keep devkb at hand |
| **Feature builds** (C/C++ support, 30-criterion request) | $1.89, 58 turns | $2.26 (+20%), 58 turns, 0 devkb calls | not measured | devkb is not used in builds |
| **Story implementation** (SPEC-DKB-004 story 1, round 1) | not measured | $2.42 (guardrail off), $2.12 (guardrail on); 0 devkb calls in 4 runs | not measured | devkb is not used; round 1 ran on a broken corpus copy (§2.6) |
| **One-lookup navigation** (click, 8 questions) | $0.0096, 2.4 turns | $0.0085 (−11% warm cache), 2.1 turns | not measured | small saving when asked |
| **Multi-hop: a function and its callees** (click) | $0.0482, 3.88 turns | $0.0438 (−9%), 3.25 turns | not measured | small saving when asked |
| **Chain questions: everything that reaches F** (C/C++) | median $0.138 | **median $0.087 (−37%)**, tighter lists | not measured | **clear saving when asked** |
| **Audit** (0.2.0–0.2.10, dogfood) | not measured | not measured | 31–39% of navigation calls; 67% of 141 checked answers right, no wrong location | used; cost against grep only not measured |

**Reading.** devkb saves money only where it is asked and its answer replaces several searches: chain, impact and
audit questions. On small fixes and builds agents do not ask it, so the only effect is the cost of offering it, and
there the CLI costs nothing (fixed prompt +0.1k tokens per call) while MCP costs its 12 tool definitions (+3k tokens on
every call). **Default: CLI.** MCP is worth its overhead only for sessions dominated by chain and impact questions.
The cheapest unmeasured cell is the CLI on chain questions; it should cost the same as MCP or less (same answer text,
no definitions), but that has not been run.

## 2. The data behind each row

### 2.1 Bug-fix benchmarks (`bugfix-benchmark.md`): no devkb against MCP, 138 runs

| Test | Runs | Fixed: none / MCP / MCP + pre-edit hook | devkb used (runs where offered) | Cost per run: none / MCP / hook |
|---|---|---|---|---|
| A: audit tickets, "where to start" given | 24 | 8 / 8 / – of 12 | 0 of 12 | $0.151 / $0.152 / – |
| B: no "where to start" | 24 | 11 / 8 / – of 12 | 1 of 12 | $0.169 / $0.186 / – |
| T1: symptom-only tickets | 36 | 12 / 11 / 12 of 12 | 2 of 24 | $0.171 / $0.178 / $0.206 |
| T3: cross-file renames | 18 | 6 / 6 / 6 of 6 | 0 of 12 | $0.153 / $0.136 / $0.159 |
| T2: sympy, 1,517 files | 36 | 12 / 12 / 12 of 12 | 5 of 24 | $0.148 / $0.173 / $0.193 |

### 2.2 Fixes to devkb with the repository policy (#126): four arms, 24 runs

Three devkb defects (#114, #115, #116), 2 runs per defect and arm. Every ticket's reproduce steps are devkb
commands, so "devkb navigation" counts only devkb calls that look for code in the devkb checkout itself, not the
reproduction on the corpus.

| Arm | What the session has | Turns | Model calls | Fixed context per call | Context replayed per run | Grep | Read | devkb navigation | Reminders | Cost | Suite | Fixed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | `main`: no policy, no MCP, no graph | 28.0 | 24.5 | 21.9k | 935k | 11.0 | 6.2 | 0.2 (1/6 runs) | 0 | $0.333 | 6/6 | 3/6 |
| MCP, first policy | policy, MCP, graph, reminder at every search | 36.0 | 31.2 | 24.9k | 1.37M | 11.8 | 7.0 | 1.2 (3/6) | 12.0 | $0.416 | 6/6 | 2/6 |
| MCP, revised policy | devkb logs queries itself (#127), one reminder | 29.2 | 25.3 | 23.0k | 1.03M | 11.0 | 6.0 | 0.0 (0/6) | 1.0 | $0.366 | 6/6 | 4/6 |
| **CLI, revised policy** | the same without the MCP server | **26.3** | **21.7** | **22.0k** | **768k** | 8.8 | 6.7 | 0.0 (0/6) | 1.0 | **$0.281** | 6/6 | 3/6 |

Per defect (fixed, mean cost, mean model calls):

| Defect | none | MCP, first | MCP, revised | CLI |
|---|---|---|---|---|
| #114 enclosing function and order | 0/2, $0.39, 30.5 | 0/2, $0.47, 37.0 | 0/2, $0.30, 21.5 | 0/2, $0.24, 19.0 |
| #115 merged span | 2/2, $0.31, 22.5 | 2/2, $0.43, 31.0 | 2/2, $0.41, 29.5 | 2/2, $0.30, 24.5 |
| #116 search hint | 1/2, $0.29, 20.5 | 0/2, $0.35, 25.5 | 2/2, $0.38, 25.0 | 1/2, $0.30, 21.5 |

No run met #114 in full: every run fixed the labels and showed the calls, none ranked calls before declarations.

### 2.3 Where the cost goes

Cost per run is the number of model calls times the context each call replays (cache reads are about half of the
cost, cache writes and output the rest). A tool call is a model call, and each re-reads the whole conversation:
38–43k tokens here, about $0.007–0.01 a call.

- **Fixed context is most of every call.** System prompt, tool definitions and instructions are 22–25k of the
  38–43k tokens per call, about 57% of all input in every arm.
- **MCP's extra cost is its definitions and the turns they invite.** The first MCP arm cost 25% more than none:
  22% of the extra context came from 3k more fixed tokens on every call, 78% from 7 more model calls per run.
- **devkb calls were added on top of grep, not instead of it.** Navigation calls rose from 18.5 to 22.0 per run
  while grep stayed at 11. A devkb call saves money only when it replaces at least one other call.
- **Some turns devkb cannot remove.** Claude Code requires a Read before an Edit, so the file being changed is read
  however good the graph's answer is.

### 2.4 Run-to-run variation (same setup, same ticket)

| Pair | Tool calls | Cost | Outcome | Where they diverged |
|---|---|---|---|---|
| #114 CLI r1 / r2 | 17 / 29 | $0.19 / $0.30 | both partial | identical first 2 steps; r2 explored with throwaway probes and rewrote its test three times |
| #116 CLI r1 / r2 | 30 / 20 | $0.33 / $0.28 | fixed / not | identical first 4 steps; r1 changed the hint itself, r2 only the data behind it and committed without seeing the fix in the real output |

### 2.5 Read tools on click (`read-tools-benchmark.md`): no devkb against MCP, 16 runs per arm

| Question set | Turns: none → MCP | Cost: none → MCP | Score |
|---|---|---|---|
| Navigation, one lookup each | 2.4 → 2.1 (−12%) | $0.0096 → $0.0085 (−11%, warm cache) | 0.96 / 0.96 |
| Multi-hop (function and callees) | 3.88 → 3.25 (−16%) | $0.0482 → $0.0438 (−9%) | F1 0.887 → 0.863 (n.s.) |
| Multi-hop, built-in tools restricted | 4.44 → 3.38 (−24%) | $0.0237 → $0.0236 (0%) | F1 0.885 → 0.902 (n.s.) |

### 2.6 C/C++ (`CPP-FINAL-REPORT.md`, `bench/exercises/cpp/DEVKB-VALUE.md`): no devkb against MCP

Chain questions ("every production function that can reach F, and its test files"), 5 questions, 20 runs:

| Question | Cost: none / MCP | Precision: none / MCP | Recall: none / MCP |
|---|---|---|---|
| leveldb `WriteRawBlock` | $0.125 / $0.064 | 0.51 / 0.94 | 1.00 / 0.88 |
| leveldb `LogAndApply` | $0.121 / $0.103 | 0.20 / 0.33 | 1.00 / 0.94 |
| leveldb `Footer::DecodeFrom` | $0.229 / $0.179 | 0.61 / 0.67 | 0.99 / 0.90 |
| cJSON `print_value` | $0.053 / $0.051 | 0.94 / 0.86 | 0.78 / 1.00 |
| cJSON `cJSON_Delete` | $0.180 / $0.107 | 0.97 / 0.99 | 0.96 / 0.97 |
| **Median** | **$0.138 / $0.087 (−37%)** | | |

Feature builds (the same 30-criterion request), means by arm:

| Arm | Runs | Wall | Turns | Model calls | Grep | File load | devkb | Tokens (ctx / out) | Cost |
|---|---|---|---|---|---|---|---|---|---|
| none | 2 | 16 min | 58 | 44 | 9.5 | 10.5 | 0 | 4.9M / 85k | $1.89 |
| MCP | 4 | 14 min | 58 | 49 | 15.2 | 8.2 | 0 | 6.6M / 96k | $2.26 |

SPEC-DKB-004 story 1, round 1 (4 runs, MCP with the guardrail off and on): 0 devkb calls; $2.42 and $2.12 per run.
The corpus was copied without its `.git` in that round, so devkb's corpus graphs had 3 nodes and the truth script saw
no files. No agent asked devkb about the corpus, so the use figure stands, but the outcome scores do not; the story
is to be re-run on the fixed harness.

### 2.7 Audit (`devkb-for-auditing.md`): devkb from the shell

Agents working devkb-first sent 31–39% of their navigation calls, and 22–32% of the navigation text, through devkb.
Of 141 checked answers 95 were right (67%), and none pointed to a wrong location. Cost was not compared with a
grep-only audit.

## 3. What is not measured yet

| Cell | Why it matters | Estimate |
|---|---|---|
| CLI on chain and multi-hop questions | confirms the CLI keeps MCP's saving where devkb pays | ~$8 |
| Audit, CLI against no devkb | the task where devkb is most used; no cost comparison exists | ~$10 |
| Story implementation, CLI against no devkb (fixed harness) | new development | ~$10 |

## 4. Reproduce

`bench/policy/`: `policybench.py` (the four #126 arms), `storybench.py` (story runs), `accept/` (hidden checks per
ticket), `tokens.py` (per-call token structure), `report.py` (tables); raw results `results-policy.jsonl`,
`tokens-policy.json`, `results-117-round1.jsonl`. The guardrail is `scripts/devkb_guardrail.py`.
