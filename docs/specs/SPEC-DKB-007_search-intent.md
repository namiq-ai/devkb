---
id: SPEC-DKB-007
title: "Every answer the guardrail gives is the question the search asks, and an agent can ask the graph by intent"
type: specification
doc_type: prd
track: brownfield
status: proposed
created: 2026-11-18
updated: 2026-11-18
owner: PO
source: owner request 2026-11-18 ("file 1 ticket about the wrong intent translation / mapping between grep and graph query … deal with this matter as a specification") and addition ("explore more about the possibility to do intent => graph; of course I don't intend to remove the current flow")
supersedes: []
superseded_by: null
extends: "SPEC-DKB-005 (#162, PR #164: when a search may be replaced), SPEC-DKB-006 C1 (#166: the definition answer)"
tickets: ["#211"]
related: ["#212 (traceback, out of scope)", "#180", "#181", "#182", "#183", "#184", "#185", "#186"]
---

# SPEC-DKB-007: from a search's intent to a graph question

BMAD roles: brief (§1), requirements (§2), architecture (§3), stories (§4), readiness (§5), evaluation (§6), results
(§8). Baseline: `main` at `268edf8` (v0.2.12).

## 1. Brief (analyst)

SPEC-DKB-005 decided **when** the guardrail may replace a search: only when devkb's answer is the same question. It
did not decide **what** to answer otherwise. At v0.2.12 every search whose pattern names an identifier that resolves
Complete gets devkb's direct-caller pack, as a replacement or alongside, whatever the search was for:

- the names come from the pattern alone (`navigation_names`, `devkb/misses.py:33`); the flags, operands and pipes only
  pick *replace* or *alongside* (`answer_or_record`, `scripts/devkb_guardrail.py:522-541`);
- the only question asked of the graph is `pack refactor`, for every name (`QUESTION`, `scripts/devkb_guardrail.py:190`);
  the one exception is a single-name definition search, which gets the location and body (#166);
- the pack is the same Markdown in every case: title, freshness line, "Defined at", callers, tests, Coverage and a
  fixed footer (`Packer.refactor`, `devkb/packs.py:409-450`).

**Measured on the 941 code searches of the 0.2.12 release benchmark**, replayed through the v0.2.12 hook. 120 get a
devkb answer. Each was labelled by the intent of the command segment that triggered it, by rules and then by hand
(the data is in the benchmark workspace, `intent-0.2.13/labels.json`):

| The search asks | Answers | devkb gave | Verdict |
|---|---|---|---|
| a body (`grep -n "def X" -A40`, `"class X" -A60`) | 38 | callers of X | different question |
| a body | 13 | location and body | same question |
| call sites, repository-wide | 18 | callers of X | same question |
| call sites, filtered (`… \| grep -v tests`) | 14 | all callers, unfiltered | partly |
| lines in one named file (`grep -n X file.py`) | 11 | callers across the repository | partly |
| where X is defined (`grep -n "^X\|^Y" file`) | 9 | a "Defined at" line inside a callers pack | partly |
| where X is defined | 3 | location and body | same, larger than asked |
| the functions in a file (`grep -n "^def " file`) | 10 | callers of a symbol named `Def`, or of another file's `pack` | different question |
| literal text (`grep -n devkb .gitignore`) | 3 | a pack | different question |
| a count (`grep -c read_answer file`) | 1 | the pack for `READ_ANSWER` | different question |

**34 of 120 answer the question asked, 34 partly, 52 not.** The wrong answers are also large: 64% of a pack's text is
fixed wording (6.2k of 9.7k characters across the #143 answers), and the one right-question answer in #143 was 4× the
size of grep's own output. In the release benchmark the tickets where devkb answered most cost slightly more than the
runs without devkb (#143 +6%, #162 +6%).

**Five forms seen so far** (the ticket's examples, all reproduced at v0.2.12):
1. A body read gets callers (#143).
2. A search confined to one named file is answered from another file (`grep -n "pack" devkb/packs.py | grep "def "`
   gets `devkb/mcp_server.py::build.pack`).
3. The answer's shape ignores the question: fixed text, and call lines collapsed into "+2 more", fewer than grep gives.
4. An instruction that does not match the agent's intent is ignored and paid for: the enforcing redirect of #130
   (#117) led to 6 identical re-runs in 13 denials.
5. A keyword or a differently-cased word is resolved as a name: the resolver's "exact" tier compares in lower case
   (`ReadTools.resolve`, `devkb/read_tools.py:168`), so `def` resolves to `class Def` and `read_answer` to
   `READ_ANSWER`.

**The direct path is not used.** In 27 of the 28 devkb runs of the release benchmark, the agent never ran a devkb
query of its own; the one exception was a run of #117 (8 queries, one of them useful). Every saving devkb made came
through the hook. An agent's flow today is *intent → grep → (hook) → graph*.

**Mitigation in place:** the owner's user-level hook copy answers alongside only (substitution off) until #180–#182 are
fixed. It does not stop wrong answers alongside.

## 2. Requirements (PM)

**Principle (kept from SPEC-DKB-005).** Every doubt resolves toward running grep with no devkb text. A wrong decision
may lose a saving; it must not add a wrong or unneeded answer.

| # | Requirement | Falsified by |
|---|---|---|
| R1 | Each search is given one **intent** (§3.2) from the whole command: pattern, flags, operands, pipes and the tool. The names alone never decide what is answered. | a body read, a file listing, a count or a literal getting a callers pack |
| R2 | Each intent maps to at most one graph question and one answer shape (§3.3). An intent with no graph question, or `unknown`, gets no devkb text. | devkb text on an intent the table marks *none* |
| R3 | A name matches a symbol only in the case the search uses, unless the search is case-insensitive (`-i`). A language keyword (`def`, `class`, `function`, `fn`, `struct`, …) is never a name. | `^def ` answered for `Def`; `read_answer` answered for `READ_ANSWER` |
| R4 | A search confined to files answers only from those files, and a pipe that filters (`grep -v`, a second `grep`) is applied to the answer or the answer is withheld. | an answer naming a file the search excluded |
| R5 | An answer given **alongside** carries only its content: no title, freshness sentence, Coverage paragraph or footer, and never more characters than grep's own output for the same command (measured on the replay corpus). A replacement may keep one line saying it is Complete. | an alongside answer with fixed pack text; one larger than grep's output |
| R6 | Call sites are given as `file:line: text` lines, as grep prints them, never collapsed into "+k more". | a call site grep prints that the answer leaves out |
| R7 | Every decision line logs the intent and the graph question asked. `devkb guardrail-stats` counts every action (including read-answer, span-hint and remind) and every intent. | a decision line with no intent; a read-answer missing from the stats |
| R8 | On the replay corpus the share of answers to a different question is at most 5%, and no answer is added where v0.2.12 added none, unless its intent is answered by the table. | the §6 replay above the floor |
| R9 | SPEC-DKB-005 R1–R9 and SPEC-DKB-006 C1 still hold: the replacement rule, the scope filter, the repeat escape, the miss log, the definition answer. | their tests failing |
| R10 | The current flow stays. A **direct path** (*intent → graph*, §3.6) is offered next to it and kept only if the evaluation shows agents use it and it costs no more. | the hook removed or weakened to favour the direct path |

## 3. Architecture (architect)

### 3.1 The flow

```
event ─► parse (SPEC-DKB-005) ─► classify ─► intent ─► mapping table ─► graph question ─► shape ─► decide ─► log
                                     │                       │                                        │
                                     │                       └─ none / unknown ──────────────────────►│ pass-through, no text
                                     └─ pattern, flags, operands, pipes, tool                          ├─ substitute (same question, SPEC-DKB-005)
                                                                                                       └─ alongside (compact, R5)
```

The parse stays as it is (`bash_search`, `grep_tool_search`). Two gaps in it matter here and are fixed with it:
`bash_pattern` does not know which flags take a value (`grep -A 30 foo` gives the pattern `30`), and only the first
search of a compound command is read.

### 3.2 Intent classes

A pure function `classify(search) -> Intent`, in the hook, with no graph access. First match wins:

| Intent | Recognised by | Example |
|---|---|---|
| `not-a-search` | no search stage after quotes and heredocs are removed | `python - <<E … grep … E` |
| `non-code` | scope or `--include`/`glob`/`type` admits no code language | `grep -rn x docs/` |
| `count` | `-c`, `output_mode: count`, a pipe into `wc` | `grep -c read_answer f.py` |
| `list-files` | `-l`, `-L`, `files_with_matches` | `grep -rl X .` |
| `invert` | `-v` on the search | `grep -rnv X f.py` |
| `list-symbols` | a keyword-only pattern (`^def `, `^\s*def `, `^class `, `"    def "`) | `grep -n "^def " f.py` |
| `read-body` | one definition pattern with `-A`/`-B`/`-C` or `context` | `grep -n "def X" -A40 f.py` |
| `locate` | a definition pattern, or a name anchored at line start (`^X`), with no context | `grep -n "def X" .`, `grep -n "^X\|^Y" f.py` |
| `in-file` | identifier names, one file operand | `grep -n X f.py` |
| `call-sites-filtered` | identifier names, followed by a filtering pipe (`grep -v`, `grep`) | `grep -rn X . \| grep -v tests` |
| `call-sites` | identifier names, folders or the repository | `grep -rn X pkg/` |
| `literal` | a pattern that is not identifiers (a phrase, a string, a regex) | `grep -rn "could not read" .` |
| `unknown` | anything else | |

Rules were chosen over a learned classifier: they are testable case by case, need no model at hook time (the hook must
answer within its 20-second budget and stay standard-library), and every rule can be traced to labelled searches. A
learned classifier stays an option only if the rule table's mismatch rate stops falling.

### 3.3 Mapping table

| Intent | Graph question | Answer shape | Replace or alongside |
|---|---|---|---|
| `read-body` | `symbol NAME --source` (exists, #166) | location and body, 80-line cap | replace (as today) |
| `locate` | `symbol NAME` | `file:line: signature`, one line per definition | replace when one exact match, else alongside |
| `list-symbols` | `outline FILE` | `Lstart-Lend kind name`, one line per symbol | alongside |
| `call-sites` | `uses NAME --json` (calls first) | `file:line: text` lines, as grep prints them | replace when SPEC-DKB-005 allows, else alongside |
| `call-sites-filtered` | `uses NAME --json`, with the pipe's filter applied to file paths | `file:line: text` lines | alongside |
| `in-file` | `uses NAME --json`, filtered to the file | `line: text` lines for that file | alongside |
| `count`, `list-files`, `invert`, `literal`, `non-code`, `not-a-search`, `unknown` | none | none | pass-through, no text |

Notes:
- `count`, `list-files` and `invert` get **no** answer. Grep counts every text line, comments and strings included, so a
  graph count is a different number (SPEC-DKB-005 §3.6). The answer would only add tokens.
- The caller **pack** (`pack refactor`) leaves the hook's answers. It stays the answer to `devkb pack refactor` asked
  directly, so `Packer.refactor` does not change. devkb's own graph shows 7 files calling it, 5 of them tests, while
  the hook is one caller of `run_query`.
- Case (R3) is checked in the hook, after resolution: a match whose name differs in case from the searched name is
  dropped unless `-i` is set. `ReadTools.resolve` keeps its case-folding tier. devkb shows its two callers, `symbol`
  (`devkb/read_tools.py:256`) and the packs (`devkb/packs.py:283`), and both serve agents who type names loosely.
- `navigation_names` stops stripping a keyword when nothing else is left, so `^def ` gives no name and classifies as
  `list-symbols`.

### 3.4 Shape budget

An alongside answer is cut so it is never larger than grep's own output for the same command. When grep's output is
not known before the tool runs (PreToolUse), the hook uses a fixed cap of 1,500 characters, and the evaluation checks
the ratio after the fact (§6). A replacement keeps a one-line header: "devkb answered this search from the graph
(Complete); repeat the command for grep's lines."

### 3.5 Logging

Each decision line gains `intent` and `question` (for example `uses`, `symbol`, `outline`, `none`). `devkb
guardrail-stats` counts every action it finds and adds a table of intents by action. That table is the evidence for
any later change to §3.3.

### 3.6 The direct path: intent → graph

Today the agent turns an intent into grep, and the hook turns grep back into a graph question. The direct path skips
the first step: the agent asks the graph by intent. The read tools exist (`symbol`, `uses`, `outline`, `pack`, on the
CLI and as MCP tools), and AGENTS.md tells agents to use them. Agents still don't: 0 direct queries in 27 of 28 devkb
runs. So the question is not whether the tools exist, but what makes an agent reach for them at the moment of intent.

Candidates, evaluated as benchmark arms (§6) next to the hook, never instead of it:

| # | Candidate | How it reaches the agent at the moment of intent | Risk |
|---|---|---|---|
| D1 | **Answers that teach.** Each alongside answer ends with the one devkb command that gives it (`devkb uses X --project .`), one line. | The agent sees which command answers its intent, on the search it just made. | adds a line per answer; may be ignored like AGENTS.md |
| D2 | **Outline on first open.** The first whole-file Read of a code file in a session gets the file's outline alongside (span-hint, generalised). | The intent "what is in this file" is asked by opening it. | a cost on every first read; overlaps `devkb hook pre-edit` |
| D3 | **Intent-named tools.** MCP tools named by the question (`find_definition`, `read_body`, `list_symbols`, `find_call_sites`), each description starting with the intent in the agent's words. | Tool choice is made by name and description at planning time. | each tool's definition is sent on every turn, a cost paid whether or not the tool is used |
| D4 | **One intent command.** `devkb ask "where is X defined" / "who calls X" / "what is in FILE"` maps a plain question to §3.3's table. | One command to remember instead of four. | a second classifier, in prose |

D1 and D2 are cheap to build on the §3.3 work and are tried first. D3 and D4 are tried only if D1 or D2 shows that
agents do switch to direct queries when shown the command at the right moment.

## 4. Stories

| Story | Scope | Depends on |
|---|---|---|
| S1. Classify and log, no behaviour change | `classify()`, `intent` and `question` in the log, stats counting every action and intent; tests for every row of §3.2 | — |
| S2. Names: case and keywords | R3: case check after resolution; keyword-only patterns give no name; `bash_pattern` skips option values | S1 |
| S3. Answers by intent | §3.3 table: `locate`, `list-symbols`, `call-sites`, `in-file`, `call-sites-filtered`; the pack leaves the hook | S1, S2 |
| S4. Compact shape | R5, R6, §3.4: grep-like lines, no fixed text alongside, size budget | S3 |
| S5. Direct path, first arms | D1 and D2 behind a setting; benchmark arms | S3 |
| later | D3, D4, from S5's results; a learned classifier only if §6's mismatch rate stops falling | S5 |

#212 (the traceback on a repository with no graph) is separate and not blocked by this specification.

## 5. Readiness (G0)

- The problem is measured on 941 replayed searches (§1). The labels and the replay harness are in the benchmark
  workspace (`intent-0.2.13/`, `replay-0212/`).
- The code as it stands is documented with every claim cited and verified (codebase research at `268edf8`: decision
  flow, parsing, queries and answer shapes, history of the same-question rule, logging, tests; 19 load-bearing claims,
  16 verified, 3 corrected).
- What the tests do not feed today (that research, §6): egrep; `rg` and `git grep` against a built graph; Bash `-i`;
  code `--include` globs; `class`/`struct`/`function` definition patterns; keyword-only patterns; several names. S1's
  tests cover them.
- No schema change: no node type, no edge verb, no ADR.

## 6. Evaluation

1. **Replay (every story).** The 941 searches through the branch's hook. Report, per intent: answers given; same,
   partly or different question (labelled as in §1); the alongside size against grep's output. Floor: at most 5%
   different-question answers (R8), and no alongside answer above grep's size.
2. **Hidden check.** A fixture with the §1 forms: a body read, a definition, a file's functions, one-file lines,
   filtered call sites, a count, a literal, `^def `, a lower-case name that differs from a symbol only in case, and a
   compound command whose second search is the navigation one. Each case asserts the intent, the question and the
   answer's first line.
3. **Dual mode,** per the policy (no devkb against devkb CLI), Sonnet, the issue as filed. **3 runs per arm,** not 2:
   the 0.2.12 release table showed run-to-run swings of ±20–37% on single tickets, larger than any devkb effect.
4. **Direct-path arms (S5):** hook only; hook + D1; hook + D2. Measured: direct devkb queries per run, the share of
   navigation intents answered by a direct query, cost and context. D1 or D2 is kept only if direct queries rise and
   cost does not.

## 7. How devkb was used to write this specification

- The guardrail itself, replaying 941 searches, to measure what it answers (§1).
- `devkb pack refactor` on `answer_or_record`, `navigation_names`, `ReadTools.resolve` and `Packer.refactor` (all
  Complete), to find what a change would touch. This is why §3.3 keeps the case check in the hook and leaves
  `Packer.refactor` alone.
- `devkb symbol def` and `devkb uses --json`, to reproduce form 5 and to check that `uses` already returns grep-like
  hit lines.
- Grep, and reading the files, for the bodies of `bash_pattern`, `answer_or_record` and `ReadTools.resolve`: a body is
  not a graph question.

## 8. Results

To be filled in story by story: the replay table per intent, the hidden-check results, and the dual-mode and
direct-path tables.
