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
- **Not shown:** whether devkb helps when navigation is hard. Three follow-up tests isolate the reasons above:
  symptom-only tickets in a user's words (ticket quality), the same kind of bugs in a large unfamiliar repository
  (repository size), and changes with cross-file impact such as a signature change with all its callers (the graph's
  intended use). Planned after 0.2.8.
- **For QAKB (#36):** a knowledge base will not be consulted for questions a single search answers; its value has to
  be shown on cross-file and impact questions, and the instructions must make those questions explicit ("before
  changing X, list everything that computes or calls X").

Cost: $3.64 (variant A) and $4.27 (variant B), 48 runs in all.
