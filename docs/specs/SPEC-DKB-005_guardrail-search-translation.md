---
id: SPEC-DKB-005
title: "The guardrail replaces a search only when devkb's answer is the same question"
type: specification
doc_type: prd
track: brownfield
status: proposed
created: 2026-11-18
updated: 2026-11-18
owner: PO
source: owner question 2026-11-18 ("how the grep folder and commandline option to be translated to graph query? is this design considered thoroughly") and request ("make this as specification the link to this ticket")
supersedes: []
superseded_by: null
extends: "#131 (substitution), #154 (direct-caller question), #149 (decision log)"
tickets: ["#162"]
---

# SPEC-DKB-005: translating a search into a graph question

BMAD roles: brief (§1), requirements (§2), architecture (§3), stories (§4), readiness (§5), evaluation (§6), results
(§8, after #162 merges). Baseline: `main` at `5ed31a3`.

## 1. Brief (analyst)

The guardrail (`scripts/devkb_guardrail.py`, a PreToolUse hook on Bash and the Grep tool) asks devkb about the names a
code search looks for. When every name resolves with coverage Complete, it **replaces** the search with devkb's
direct-caller pack (#131, made frequent by #154). It decides from the pattern alone:

- the repository comes from the session's working directory, not from the path searched;
- the folder, every option and any pipe are ignored;
- "a single search" is checked by splitting on `&&`, `||`, `;` and newlines, but not `|`.

Probe on devkb at `5ed31a3`, searching for `pure_search` (Complete): **15 of 15** searches were substituted. Only the
first asked the question the pack answers.

| Search | What was asked | What devkb answered |
|---|---|---|
| `grep -rn pure_search scripts/` | uses | uses (correct) |
| `grep -rn pure_search tests/` | uses in tests only | all callers |
| `grep -rn pure_search docs/`, `--include=*.md`, Grep tool `glob: *.md` | mentions in documents | code callers |
| `… \| wc -l`, `grep -rc`, Grep tool `output_mode: count` | a count | a caller list |
| `grep -rl pure_search .` | which files | callers |
| `grep -rni PURE_SEARCH .`, Grep tool `-i` | case-insensitive matches | the exact-case symbol |
| `grep -n -A8 'def pure_search' file`, Grep tool `-C 5` | the body, the context | one line per caller |
| `grep -rnv pure_search file` | lines without it | lines with it |
| `… \| grep -v test` | non-test uses | all callers |
| `grep -rn pure_search /path/to/another-repo` | another repository | devkb's own callers |

An agent can escape by repeating the search, but only if it notices that the answer is wrong. It usually will not:
the answer is well formed and says it is Complete.

**Mitigation in place:** the user-level hook copy on the owner's machine has substitution off until #162 merges.
Names that resolve Complete get the answer alongside, and grep always runs.

## 2. Requirements (PM)

**Principle.** Every doubt resolves toward running grep: a wrong decision may lose a saving, never give a wrong
answer (owner, 2026-11-18: "the graph must have data to return but if it is not, failed safe approach should be done
like traditional grep usage").

| # | Requirement | Falsified by |
|---|---|---|
| R1 | The repository is the one the searched paths are in, not the working directory. | a search of repository B, run from A, getting A's answer |
| R2 | Paths outside any repository with a graph, or spread over several repositories, pass through with no devkb answer. | any devkb text on such a search |
| R3 | Only a command with exactly one stage, which is one `grep`/`rg`, can be substituted; `\|` is a stage separator. | `grep … \| wc -l` substituted |
| R4 | Only options that change how grep searches or prints, not what it is asked, allow substitution (§3.3). | `-c`, `-l`, `-i`, `-v`, `-o`, `-A`/`-B`/`-C`, `files_with_matches`, `count` or `multiline` substituted |
| R5 | A search whose scope holds only non-code files passes through with no devkb answer. | devkb text on `docs/`, `*.md` |
| R6 | When the searched folders are narrower than the repository, a substituted answer lists only sites under them and says so; if none remain, the search passes through. | a `tests/` search answered with `pkg/` callers |
| R7 | Names that resolve Complete but fail R3–R4 get devkb's answer alongside; the search still runs. | grep not run, or no answer |
| R8 | Every decision line in the guardrail log (#149) carries a `reason`. | an `alongside` or `pass-through` line without one |
| R9 | Existing behaviour is kept: an identical repeated search runs as grep; an Incomplete or unknown name passes through and is logged as a miss (#133). | #131, #133 and #154 tests failing |

## 3. Architecture (architect)

### 3.1 Read the search as a query

```
event ─► parse ─► repository ─► names ─► graph verdicts ─► decision ─► log (action, reason)
          │          │                                        │
          │          └─ from path operands / Grep `path`      ├─ substitute (scoped answer, grep not run)
          └─ stages, tool, options, paths, cwd                ├─ alongside  (answer + grep runs)
                                                              └─ pass-through (grep runs; miss logged by the post hook)
```

- **Bash:** `shlex` tokens. Stages are split on `&&`, `||`, `;`, `|` and newlines. A leading `cd DIR &&` sets the
  directory paths resolve against. Of the remaining stages, the `grep`/`egrep`/`rg`/`git grep` one supplies the
  pattern (`-e` value, else the first non-option word), its options and its path operands (default `.`).
- **Grep tool:** `pattern`, `path`, `glob`, `type`, `output_mode`, `-i`, `-A`/`-B`/`-C`, `multiline`, `head_limit`.
- **Names:** `navigation_names()` as today (up to three identifiers; a regex or phrase is not a navigation search).

### 3.2 Repository

Each path is resolved and mapped to its git top level (`git rev-parse --show-toplevel`, cached per directory).
- One repository with `.devkb/` → it is the graph asked.
- Otherwise (outside any repository, several repositories, or no graph) → pass-through, reason `repo:none`,
  `repo:several` or `repo:no-graph`.

### 3.3 Is it the same question?

| Search | Reason code | Decision |
|---|---|---|
| one stage; options within `-r -R -n -H -w -E -F --color[=…]`; Grep tool `output_mode: content`; every path a directory | — | **substitute**, scoped (§3.4) |
| a pipe or a second stage | `pipe`, `compound` | alongside |
| only `head` or `tail` after the search (`-n N`, `-N`), #174 | (none: decided as the search alone) | as the search alone |
| `-c` / `output_mode: count` | `option:count` | alongside |
| `-l`, `-L` / `output_mode: files_with_matches` | `option:files` | alongside |
| `-i` / Grep `-i` | `option:case` | alongside |
| `-A`, `-B`, `-C` / Grep context | `option:context` | alongside |
| `-v` | `option:invert` | alongside |
| `-o`, `multiline`, `-P`, `-f` and any unrecognised option | `option:other` | alongside |
| a path operand that is a file | `single-file` | alongside |
| `--include`/`glob`/`type` admitting no code language, or folders with no code files | `scope:non-code` | pass-through, no devkb text |
| a name Incomplete, ambiguous or unknown | `verdict:<v>` | pass-through (miss logged after grep, #133) |
| the identical search repeated in the session | `repeat` | pass-through |

An unrecognised option counts against substitution. The list of safe options grows only with evidence (§4, later).

### 3.4 Scope

When the path operands are narrower than the repository root, the pack's site lines (`file:line`) are kept only
under those paths, and the header says `limited to <paths>`. If no site remains, pass-through, reason
`filtered-empty`: grep may still find the definition or a mention there.

### 3.5 Logging

Each decision line is the #149 line plus `reason` and `paths` (repository-relative). `devkb stats` counts actions and
reasons. Those counts drive §4's later stories: which reasons are common on Complete names, and so where a translation
would save the most.

### 3.6 Not in scope

- Translating options into graph queries (`-l` → the callers' files, `-c` → a count, a single file → the pack
  filtered to that file). Grep counts every text line, including the definition, comments and strings, so a graph
  count would not be the same number, and agents act on numbers. This waits for evidence (§4).
- The miss log's parsing of grep output (#137, #152).

## 4. Stories

| Story | Ticket | Scope |
|---|---|---|
| 1. Same-question substitution (R1–R9) | #162 | `scripts/devkb_guardrail.py` (`pure_search`, `answer_or_record`, repository detection), scope filtering, reason codes, tests |
| later. Option translations | to file after release-level data | from `devkb stats` reasons: the most common options on Complete names, each only where the answer is provably the same |

## 5. Readiness (G0)

- Problem reproduced (§1 probe) on `5ed31a3`.
- Hidden check written and validated: on `main` it fails 15 of 16 cases. The one that passes is the correct case,
  the whole repository.
- The mitigation is in place on the owner's machine.
- No schema change: no node type, no edge verb, no ADR.

## 6. Evaluation

Dual mode, per [the policy](../analysis/devkb-none-mcp-cli.md): no devkb (files kept, devkb denied) against devkb
CLI, 2 runs each, Sonnet, the issue as filed.

The hidden check (bench `accept/162.py`) builds a fixture repository A with `compute` defined in `pkg/core.py`,
called from `pkg/app.py` and `tests/test_core.py`, and mentioned in `docs/guide.md`, plus a repository B with no
graph. It runs 16 searches through the checkout's registered hooks:
- **substitute:** `.`, and `pkg/` limited to `pkg/`;
- **substitute limited to `tests/`:** `tests/`;
- **never substitute:** `docs/`, `--include=*.md`, `| wc -l`, `-c`, `-l`, `-i`, `-A8`, `-v`, `| grep -v`, and the Grep
  tool with `glob: *.md`, `count`, `-i` with `-C`;
- **repository B:** no substitution and no text about A;
- every non-substitution decision logged with a reason.

## 7. How devkb was used to write this specification

- `devkb pack refactor` on `navigation_names`, `parse_grep`, `verdict_of` and `bash_pattern` (all Complete), to
  find where the translation lives.
- The guardrail itself, through its registered hook, on the 15 probe searches in §1.
- Grep was used for the reading of `pure_search`, `bash_pattern` and `answer_or_record`. Their bodies are what the
  spec needed, and a body is not a graph question.

## 8. Results

To be filled in when #162 merges: the dual-mode table, the hidden-check results per run, and the guardrail's action
and reason counts from the runs.
