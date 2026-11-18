---
id: SPEC-DKB-006
title: "Exploration beyond grep: locate-and-read in one step, reads that do not cut a function short"
type: specification
doc_type: prd
track: brownfield
status: draft
created: 2026-11-18
updated: 2026-11-18
owner: PO
source: owner question 2026-11-18 ("ai coder not only use grep but also find command ... or a combination bw find for a list of files then do the grep. Any thing else that devkb could do in this case? initial the specification if devkb could contribute")
supersedes: []
superseded_by: null
extends: SPEC-DKB-005 (the same-question rule), SPEC-DKB-003 (read tools)
tickets: ["#166 (story 1, C1)", "#167 (story 2, C2)", "#168 (story 3, C3 measurement)"]
---

# SPEC-DKB-006: what devkb can do for exploration other than grep

Status **draft**: it states the measurement, the candidate contributions and how each would be judged. Stories filed
as #166, #167 and #168 (2026-11-18). Baseline: `main` at `5ed31a3`.

## 1. Brief (analyst): how agents actually explore

Every tool call in the 72 dual-mode agent sessions so far (Claude Code, Sonnet, on devkb and its C/C++ corpus;
tickets #114–#162):

| Activity | Calls | Notes |
|---|---|---|
| read a line range: `sed -n 'A,Bp' file` | 637 | median 36 lines, quartiles 18 / 60, max 336; 28,389 lines in all |
| `grep -n` for a definition (`def X`, `class X`, `struct X`) | 302 | **189 reads followed straight after one**: locate, then read |
| list a folder: `ls`, `tree` | 400 | |
| `cat` / `head` / `tail` a file | 349 | |
| the Read tool | 203 | 174 with offset/limit, 29 whole files |
| other grep shapes | ~450 | covered by SPEC-DKB-005 |
| find files: `find` 8, `git ls-files` 23, Glob tool 7 | 38 | **rare**: 2% of shell calls |
| `find … \| xargs grep` / `-exec grep` | 0 | |

**On the owner's hypothesis.** In these sessions, `find` and find-then-grep are rare. The dominant exploration pattern
is **locate a definition with `grep -n`, then read a guessed line range with `sed -n`**. Two caveats:
- other agents (Codex, Cursor, Aider) and unfamiliar repositories may lean on `find` more. The sessions here are one
  agent on repositories it had in front of it;
- the counts include setup and test commands from the same sessions; the shares, not the totals, are the point.

**Guessed ranges.** Of 321 `sed -n` reads of Python files checked against the files' syntax trees, **37 (16%)
started inside a function and stopped before it ended**. 29 reads (6%) continued straight on from the previous read
of the same file. The trees are those of the finished checkouts, so this is an approximation.

**devkb can already answer the dominant pattern.** `devkb symbol NAME --source` prints a definition's location and its
exact body. In 72 sessions agents called it **zero** times: agents do not reach for devkb on their own (the finding
behind #131). As with grep, a contribution has to come through the guardrail, not through agent choice.

## 2. Candidate contributions

| # | Contribution | What it replaces | Expected effect | Priority |
|---|---|---|---|---|
| C1 | **Locate-and-read in one step.** A definition search (`grep -n "def X"`, `class X`, the Grep tool on `def X`) for a name that resolves to one symbol is answered with its location **and** body (`symbol --source`), capped at 80 lines (location and span only beyond that). | the `grep -n` call and the `sed -n` read after it | one fewer turn per pair (189 pairs in 72 sessions, about 2.6 per session); no guessed range | **high** |
| C2 | **Span hint on a cut-short read.** A `sed -n A,Bp`, `head`/`tail -n` or Read-tool range that starts inside a function and stops before its end gets one line alongside: `this range stops at L…; <function> runs L…–L…`. The read itself is unchanged. | the follow-up read | fewer read-on reads (6%) and partial understanding (16% cut short) | medium |
| C3 | **Folder outline.** `ls DIR` / `tree DIR` on a code folder gets, alongside, the folder's files with their top-level symbols (`outline` per file, compact). | some of the cat/sed reads that follow a listing | unknown: measure first (§5) | low |
| C4 | **File finding.** `find -name`, Glob, `git ls-files \| grep`: devkb adds nothing a file listing does not already give. **find-then-grep** is a grep across a file set, so SPEC-DKB-005 already covers it once a `find … \| xargs grep` command's file set is read as its scope. | — | none beyond SPEC-DKB-005 | not pursued; revisit if other agents' logs show it |

`git log` / `git diff` questions (history of a file or function) are a separate topic: devkb's process graph holds
commits and tickets, and a spec of its own would come from measuring them.

## 3. Requirements (PM), for C1 and C2

| # | Requirement | Falsified by |
|---|---|---|
| R1 | C1 applies only to a definition search: the pattern is `def`/`class`/`struct`/`fn`/`function` + one name, or `^\s*NAME\s*\(`, and SPEC-DKB-005's same-question rules hold (one stage, safe options, one repository, scope). | a body returned for a uses search, a count or another repository |
| R2 | C1 answers only when the name resolves to exactly one definition in the searched scope; several definitions pass through, or are listed with locations and no bodies. | a body of the wrong overload or class |
| R3 | A C1 answer is the location line grep would have printed, plus the body, capped at 80 lines. Beyond that it gives the location and span and says so. | an answer without the `file:line` grep would show, or a body over the cap |
| R4 | C2 never blocks or alters a read. It adds one line, only when the range starts inside a function or class and stops before its end, at most once per file and range per session. | a hint on a range that covers the function, or a changed read |
| R5 | Both are logged in the guardrail decision log (#149) with action `read-answer` / `span-hint` and a reason. | an unlogged answer |
| R6 | When the graph is stale for the file (built before its last change), C1 and C2 stay silent. | a body or span from an old version of the file |

## 4. Architecture (architect)

- **C1:** in `answer_or_record`, after SPEC-DKB-005's decision says *substitute*, a definition-search pattern
  (`misses.navigation_names` already strips `def`/`class`) asks `ReadTools.symbol(name, source=True)` instead of
  `pack refactor`. The answer reuses `symbol`'s output (location, span, body). No new graph data: spans are already
  `line_start`/`line_end` on every Symbol.
- **C2:** a PreToolUse branch for the Read tool (`offset`/`limit`) and for Bash `sed -n 'A,Bp' FILE`, `head -n N FILE`
  and `tail -n +A FILE`. It looks up the innermost symbol containing line A (`outline` data, already in the graph)
  and compares its end with B. Output is `additionalContext`, never a decision.
- **Staleness (R6):** compare the file's blob or modification time with the graph's build commit
  (`misses.graph_state`); skip when changed.
- No schema change; no ADR.

## 5. Evaluation

- **Dual mode**, per [the policy](../analysis/devkb-none-mcp-cli.md), for each story's implementation.
- **Effect, the point of the spec:** a read-heavy benchmark. qbench-style questions that need a function's body
  ("what does `X` return when …"), run with C1/C2 on and off. Measured: turns, model calls, context tokens, cost and
  answer correctness. C1 earns its place if it removes about one turn per locate-and-read pair, without lower
  correctness; C2 only if read-on reads drop.
- **C3** is decided by measurement only: in the same sessions, how often a listing is followed by reads of files in
  that folder.

## 6. Stories

| Story | Scope | Depends on |
|---|---|---|
| 1. Locate-and-read (C1, R1–R3, R5–R6): #166 | `scripts/devkb_guardrail.py`, `devkb/misses.py`; tests | #162 (SPEC-DKB-005) |
| 2. Span hint (C2, R4–R6): #167 | `scripts/devkb_guardrail.py`, Read-tool and `sed`/`head`/`tail` parsing; tests | none |
| 3. Measure listing-then-read (C3): #168 | bench script over session transcripts; a decision recorded here | none |

## 7. How this draft was made

The counts in §1 come from a script over the 72 session transcripts in the bench's `runs/` (tool calls; shell commands
split into stages; `sed -n` ranges; each range checked against the finished checkout's Python syntax tree). devkb was
asked for its read tools' options (`devkb symbol --help`), which showed that `--source` already exists.
