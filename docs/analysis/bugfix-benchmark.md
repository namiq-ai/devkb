# Bug fixing with devkb against plain (2026-11-18)

Question: does devkb make an agent fix bugs better or cheaper? Six bugs found by the 0.2.5 → 0.2.8 audit, each already
fixed with a test, were given again to fresh headless agents, half with devkb and half without.

## Method

- **Tasks:** issues #50 (`init` loses user text), #54 (dot-directory paths), #70 (self-call counted as a caller,
  in two places), #57 (C# verbatim string), #63 (C++ brace-initialised member), #65 (C++ declaration read as a call).
- **Prompt:** the issue text, then "add a regression test that fails before your fix, keep the suite passing, commit".
- **Checkout:** for every run, a fresh repository holding only `main` at `4369145` as one commit (no history, no fix
  branches), with its own virtual environment.
- **Arms:** `plain`: Read, Edit, Write, Glob, Grep, git and Python; `devkb` commands denied. `devkb`: the same, plus
  `devkb init --toolset lean-pack` (AGENTS.md instructions, CLAUDE.md import, the MCP server, a graph built at setup).
  The devkb server and command are installed apart from the checkout, so an agent's edits never change the tool it uses.
- **Model and size:** Sonnet in both arms, 2 runs per ticket per arm (24 runs per variant), 150-turn and 45-minute
  caps, four runs at a time in a fixed random order that interleaves the arms.
- **Acceptance (hidden from the agent):** the fix commit's own tests, copied in after the run, checked to fail on
  `main` and pass on the fix; two were loosened to behaviour (any refusal form naming the file and line for #50; the
  caller counts, not the reference fix's wording, for #70). Then the full suite.
- **Process:** cost, turns and wall time from the transcript; tool calls by kind (`bench/audit/toolmix.py`).
- Harness, tickets, hidden tests and per-run results: `bench/fixbench/`.

## Variant A: tickets as filed (with "Where to start: file:line"), devkb 0.2.7 from PyPI

| | plain | devkb |
|---|---|---|
| Fixed (hidden tests pass) | **8 / 12** | **8 / 12** |
| Full suite passes | 12 / 12 | 12 / 12 |
| Cost per run, mean (median) | $0.151 ($0.146) | $0.152 ($0.142) |
| Turns, mean | 12.9 | 12.2 |
| Wall time, mean | 116 s | 124 s |
| grep-class calls / file reads per run | 3.1 / 2.4 | 3.2 / 2.4 |
| devkb queries | denied | **0 in 12 runs** |

- **devkb was never used.** In every devkb run the server connected, its 12 tools were offered and the AGENTS.md
  instruction to ask the graph first was loaded; no run called it. Each run opened the file the ticket named, or
  grepped next to it, as its first step.
- **The failures are the same in both arms, and real.** #70 (all four runs): `symbol`'s count was fixed, the refactor
  pack was not ("refactor packs likewise" in the ticket). #50 run 2 (both arms): the file was protected but no message
  named it. One #65 run introduced a regression (comparisons stopped being calls); one #63 run left the fake member.
- **What the greps were:** finding a named definition in a file the ticket already gave, text patterns (`lstrip`),
  the test file's conventions, checking an edit landed. Only "every use of a name" (3–4 of 43) is a graph question.
  Agents batch several `sed -n`/`grep` lookups in one shell call; one MCP call answers one question.
- **The miss that a graph is for:** #70 says the count is wrong "and refactor packs likewise". All four agents fixed
  one place and not the other. "Every place that computes the same thing" is the impact question devkb exists for, and
  nobody asked it.

## Variant B: no "Where to start", devkb from `main` (tools load with the prompt, #46)

Same six tickets with the "Where to start" paragraph removed (symptom, repro, expected behaviour and acceptance kept),
and the devkb arm on `main`'s code, where `symbol`, `outline` and `pack` load with the prompt (no tool-search turn).

| | plain | devkb |
|---|---|---|
| Fixed (hidden tests pass) | **11 / 12** | **8 / 12** |
| Full suite passes | 12 / 12 | 12 / 12 |
| Cost per run, mean (median) | $0.169 ($0.172) | $0.186 ($0.174) |
| Turns, mean | 14.8 | 16.3 |
| Wall time, mean | 120 s | 148 s |
| grep-class calls / file reads per run | 4.5 / 2.6 | 5.2 / 3.8 |
| devkb queries | denied | **1 in 12 runs** (one `symbol` call, #54) |

- **Without the pointer the task got harder for both arms** (about 2 more turns, 1 more grep per run), and devkb was
  still not used: each agent grepped for the subsystem or the repro's vocabulary and landed on the code.
- **The gap in fixes is not a devkb effect.** devkb was queried once; the failures are the same kinds as variant A
  and occur in both arms (#50: no message naming the file, three runs across the arms; #70: packs not fixed; #65: a
  declaration still read as a call). With 2 runs per cell, 11 against 8 is within chance, and across both variants
  plain fixed 19/24 and devkb 16/24 while devkb was used in 1 of 24 runs.
- **The devkb arm costs slightly more** (+10% mean, +1% median): its prompt carries the AGENTS.md instructions and the
  tool definitions, and nothing used them.

## What this shows, and what it does not

- **For the bugs in this benchmark, devkb added nothing**: it was used in 1 of 24 runs, fixes were as good without it,
  and its prompt cost a little.
- **Why, from the transcripts and the tickets.** (1) The tickets were written by an audit that had already found the
  bug in the code, so even without "Where to start" the title names the subsystem ("C# verbatim strings…", "devkb init
  keeps…") and the repro uses the code's own words; one grep finds the function. (2) The repository is small (about 60
  modules) and named by subsystem (`init.py`, `csharp_symbols.py`, `read_tools.py`). (3) The bugs are local: one
  function, one test. (4) Agents batch several `grep`/`sed -n` lookups in one shell call.
- **The one cross-file ticket is where every arm fell short.** #70 asks for the count to be fixed "and refactor packs
  likewise"; 5 of 8 runs fixed one place only. "Every place that computes the same thing" is the impact question the
  graph answers, and no agent asked it.
- **Not shown by A and B:** whether devkb helps when navigation is hard. Three follow-up tests (T1–T3 below) isolate
  the reasons above: ticket quality, repository size, and cross-file impact.
- **For QAKB (#36):** a knowledge base will not be consulted for questions a single search answers; its value has to
  be shown on cross-file and impact questions, and the instructions must make those questions explicit ("before
  changing X, list everything that computes or calls X").

Cost: $3.64 (variant A) and $4.27 (variant B), 48 runs in all.

## Follow-up tests T1–T3 (after 0.2.9 and 0.2.10)

Each test removes one reason variants A and B gave for devkb going unused. Same harness, model (Sonnet), caps and
2 runs per task per arm. A third arm, **hook**, is the devkb arm plus `devkb init --claude-hook`: before the agent's
first edit of a file, a pre-edit hook puts that file's pack in its context unasked. The pack is delivered whether or
not the agent would ever have asked.

### T1: symptom-only tickets (ticket quality)

The six tickets rewritten in a user's words: what I ran, what I got, what I expected. No subsystem in the title, no
file, no internal names (`bench/fixbench/tickets-C/`). devkb 0.2.9, 36 runs.

| | plain | devkb | hook |
|---|---|---|---|
| Fixed, scope-matched acceptance | **12 / 12** | **11 / 12** | **12 / 12** |
| Full suite passes | 12 / 12 | 12 / 12 | 12 / 12 |
| Cost per run, mean (median) | $0.171 ($0.171) | $0.178 ($0.181) | $0.206 ($0.202) |
| Turns, mean | 15.2 | 15.2 | 16.0 |
| grep-class / read calls per run | 5.5 / 3.1 | 6.2 / 2.8 | 6.4 / 2.8 |
| devkb queried | denied | 1 of 12 runs | 1 of 12 runs |
| Hook delivered a pack | | | 4 of 12 runs |

- **Scope-matched:** the first scoring used the full hidden tests and gave 10 / 7 / 9. That was my error: rewriting
  #65 and #50 as symptoms narrowed what they asked for (#65 named only the template case, not pointer and reference
  declarations; #50 described an orphan BEGIN marker, not a lone END). Scored against what each T1 ticket asks
  (`hidden/test_hidden_65_scope_C.py`, #50's BEGIN case), every arm fixed every ticket except one devkb run on #63.
- **Symptom-only tickets did not bring devkb into use.** Agents ran the repro, read the traceback or the wrong output,
  and grepped for the words in it, about one grep more per run than with variant B's tickets.
- **The hook fired in 4 of 12 runs, all on Python files** (#54, #70). On #50 and on the C#/C++ extractor tickets it
  never fired: those agents edited with `sed` or a Python heredoc in Bash, and the hook packs a file only for an
  Edit/Write call that names it.

### T3: cross-file renames (the graph's intended use)

Three renames on devkb itself where a bare-name grep returns many false hits (`bench/fixbench/tickets-D/`):
`build_symbols.extract` (20 other functions named `extract`, callers in 14 files), `DevKBGraph.edges` (119 `.edges(`
sites, including a helper module's `P.edges` and a test-local `edges()`), and `tickets_git._run` (3 other `_run`).
A fourth (#202) was dropped: a correct solution also has to rewrite about 70 test monkeypatch lambdas, which tests
the agent's patience, not its navigation. Acceptance: the old name gone at every true site, every false site
untouched (`hidden/test_hidden_20{1,3,4}.py`, `hidden/_t3common.py`), and the full suite. devkb 0.2.9, 18 runs.

| | plain | devkb | hook |
|---|---|---|---|
| Complete and suite-green | **6 / 6** | **6 / 6** | **6 / 6** |
| Cost per run, mean | $0.153 | $0.136 | $0.159 |
| Turns, mean | 15.8 | 9.7 | 9.8 |
| devkb queried | denied | 0 of 6 runs | 0 of 6 runs |
| Hook delivered a pack | | | 0 of 6 runs |

- **Every arm got every rename right, and no run asked the graph.** The lower turns in the devkb arms are not a devkb
  effect (it was not used; n = 6 per arm).
- **How the agents did it:** a qualified pattern, not a bare name (`build_symbols\.extract\(`, `(?<!\bP)\.edges\(`),
  then `sed`/`perl` or a small AST sweep, then the full suite as the safety net. In Python a call site names its
  module or receiver, so a qualified regex is precise and the suite catches what it misses. The premise "grep returns
  hundreds of false hits" holds for a bare-name grep, which agents do not use.
- **The hook never fired**: every rename was applied through Bash, which the hook does not pack.

### T2: a large unfamiliar repository (repository size)

sympy 1.13.3 (1,517 Python files under `sympy/`), six injected bugs, each 3 to 12 calls deep from the public call in
its ticket (call chains traced at run time, `bench/fixbench/sympy/README.md`). Tickets are user reports with no
path and no internal name, and checked so that none of their words is on the faulty line. Acceptance: sympy's own tests
for the faulty code, restored from the tag before they run. devkb 0.2.10 (0.2.9 could not build sympy: #104–#106), 36
runs. Harness: `bench/fixbench/fixbench_sympy.py`.

| | plain | devkb | hook |
|---|---|---|---|
| Fixed (sympy's tests pass) | **12 / 12** | **12 / 12** | **12 / 12** |
| Fault file edited | 12 / 12 | 12 / 12 | 12 / 12 |
| Cost per run, mean (median) | $0.148 ($0.144) | $0.173 ($0.162) | $0.193 ($0.195) |
| Turns, mean | 13.2 | 13.0 | 13.7 |
| Wall time, mean | 109 s | 111 s | 163 s |
| grep-class / read / run calls per run | 3.8 / 3.8 / 3.2 | 3.7 / 3.8 / 3.8 | 4.1 / 3.6 / 4.0 |
| devkb queried | denied | 3 of 12 runs (5 calls) | 2 of 12 runs (3 calls) |
| Hook delivered a pack | | | **11 of 12 runs**, always on the fault file |

Per bug (mean cost, plain / devkb / hook): functions 0.10 / 0.16 / 0.20, matrices 0.20 / 0.16 / 0.23, printing
0.09 / 0.09 / 0.10, sets 0.14 / 0.16 / 0.18, simplify 0.20 / 0.30 / 0.26, solvers 0.16 / 0.16 / 0.19.

- **A 25× larger repository did not make the bugs harder to find.** Fewer turns than on devkb's own repository, and
  every run in every arm fixed its bug.
- **How agents navigated: by running the code, not by reading it.** They evaluated the parts of the failing
  expression in `.venv/bin/python -c` until the wrong value appeared (bisecting at run time), and only then opened the
  module. A wrong number narrows to the faulty function faster than a call graph does, because the graph lists every
  path and the run takes only the real one.
- **A confound: the model knows sympy.** One plain run on `functions-01` (12 calls deep) ran two experiments, then
  opened lines 140–168 of `trigonometric.py`, where the fault was. sympy is a well-known public project; an
  unfamiliar *private* repository of the same size is still untested.
- **The hook worked here** (agents used the Edit tool) **and made runs dearer, not better**: +30% mean cost, +50% wall
  time, the same fixes. A pack arrives just before the first edit, when the agent has already found the fault. That is
  the moment a pack can only confirm, not guide. The devkb arm cost +17% for 5 calls in 36 runs.

## Conclusions across all 138 runs

| Test | Runs | Fixed: plain / devkb / hook | devkb used (runs) | Cost vs plain: devkb / hook |
|---|---|---|---|---|
| A: audit tickets | 24 | 8 / 8 / – of 12 | 0 of 12 | +1% / – |
| B: no "where to start" | 24 | 11 / 8 / – of 12 | 1 of 12 | +10% / – |
| T1: symptom-only | 36 | 12 / 11 / 12 of 12 | 1 + 1 of 24 | +4% / +20% |
| T3: cross-file renames | 18 | 6 / 6 / 6 of 6 | 0 of 12 | −11% / +4% (not tool effects) |
| T2: sympy | 36 | 12 / 12 / 12 of 12 | 5 of 24 | +17% / +30% |

- **For bug fixing and renames by a Sonnet agent, devkb did not change outcomes** in any test, and it was used in 8 of
  84 runs where it was offered. Where it was offered and unused, its instructions and tool definitions cost 1–17%.
- **The pre-edit hook is not worth enabling by default for bug fixing**: when it fires (T2) it adds about 30% cost and
  no fixes; when agents edit through Bash (T1, T3) it does not fire at all.
- **Why the graph lost, in one line each:** the tickets name a symptom that a run reproduces (T1, T2); Python call
  sites are qualified, so a qualified grep is precise (T3); the test suite catches what a search misses (T3); and the
  model may already know a famous repository (T2).
- **Where the graph has measured value is elsewhere**: auditing, where devkb answered 31–39% of navigation calls with
  no wrong location (`devkb-for-auditing.md`), and questions with no runnable symptom (what calls this, what is
  untested, what changed between versions).
- **Still untested:** a large private repository the model has never seen; languages whose call sites are not
  qualified (C, C++); and impact questions phrased without a test suite as the safety net.
- **For QAKB (#36):** do not pitch a knowledge base as a bug-fixing accelerator. Pitch it where there is no symptom to
  run: audit, review, release impact and coverage questions. SPEC-QAKB-001 §6 records this as a risk.

Cost: T1 $6.65, T3 $2.69, T2 $6.16 (90 runs).
