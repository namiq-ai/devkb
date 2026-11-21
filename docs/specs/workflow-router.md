# Workflow router: push the graph's answer at the SDLC stage, do not wait to be asked

Status: implemented on `feat/workflow-router` (`devkb/router.py`, `devkb hook prompt`). **Measured, and off by default**: in 72 runs on four tickets it showed no effect on cost, turns or quality (docs/analysis/workflow-router-benchmark.md). `devkb init --claude-hook` and the plugin install `devkb hook context` instead, which only records the task's words for `symbol`'s ranking and pushes nothing; `--router` installs this router.

## Problem

Agents given devkb as a tool do not call it (`docs/analysis/why-agents-do-not-query-devkb.md`: 0 of 63 runs; advice at
the point of need was seen 35 times and not followed). Offering a tool costs tokens without use. The reference
architecture (the Claude Code SDLC workflows document, section 8, and its one-page summary) says the same: **push
context with deterministic hooks, do not teach commands**.

## Design

`UserPromptSubmit` hook -> `classify(prompt)` -> one route -> a bundle of at most 3,000 characters (under 800 tokens),
or nothing. Every decision is logged to `.devkb/router.jsonl`, `none` included.

| Route | Signal in the prompt | Bundle | SDLC stage |
|---|---|---|---|
| `located` | `path.ext:LINE` | none: the agent already knows where to look (gating rule). The pre-edit hook still gives the pack at the first edit | Issue -> PR |
| `error` | traceback, `XError: msg` | `pack error`: what raises it, handlers that reach it | Triage |
| `ticket` | `#123`, `KEY-123` | `pack ticket`: commits, changed functions, tests of earlier work | Triage, Issue -> PR |
| `change` | "review feedback", "CR", on a branch with a diff | `pack file` of the branch's changed source files: callers outside the diff, tests | CR -> PR |
| `release` | "release", "changelog", "bump" | commits since the last tag, SemVer suggestion (git only, no graph) | PR -> Release |
| `navigate` | backticked or snake/Camel names the graph resolves exactly | `path:line`, caller count; never a body | Issue -> PR, Epic |
| `none` | anything else | nothing | |

Rules: a fuzzy match is never a lead; an unknown error or ticket adds nothing; a graph built at another commit than HEAD
says so in one line; no graph means no answer and no failure; `DEVKB_ROUTER=0` turns it off (a benchmark's control arm).
The router never replaces `git diff`, the test runner or `gh pr checks`.

Install: the plugin (`plugins/devkb/hooks/prompt.sh`, needs the release that ships it) or `devkb init --claude-hook`.
Freshness: `devkb init --hooks` installs the post-commit rebuild.

## Not built (and why)

- `find_similar_issues` over open tickets and `GOVERNS`/`CONSTRAINED_BY` doc edges: the graph has tickets, PRs and docs
  search, but no governing-document edge (ontology change, needs an ADR: `devkb/ontology.md`).
- `audit_release_impact` for public API / schema changes: the `release` route classifies by commit prefix only and says so.
- Epic -> features (`get_domain_impact_subgraph`): a prompt-time guess at an epic's modules is the weakest signal; it belongs in
  the architect skill, calling `pack refactor` per module.

## How to know it works

Per the per-ticket checklist (`AGENTS.md`): hidden check, then two arms (`none`, `main`) with `DEVKB_ROUTER` on and off
over navigation-heavy tickets; the measure is **bundles pushed, bundles referenced in the answer, tokens and turns**,
read from `.devkb/router.jsonl`. Small located tickets are expected to show no effect (route `located`).

## Validation per workflow (2026-11-20, on devkb's own repository, graph at 812c359)

Each prompt was run through `devkb hook prompt` and every claim in the bundle checked against the source.

| Workflow | Prompt | Found | Fixed |
|---|---|---|---|
| 1 Triage, error | `ValueError: no tracked file with symbols by that path` | `pack error` named 3 unrelated raisers; the text is *returned* at `read_tools.py:370`, never raised | proof gate: a raiser is kept only if its file contains the message; none left, nothing pushed |
| 1 Triage, error | `is neither a repository path nor a registered project` | 3 raisers listed, only `project_context.py:190` has the text | the two others dropped, reach section replaced by a `refactor` pointer |
| 1 Triage, ticket | `#150` | graph keys tickets `GH-150`; lookup of `150` found nothing | tries `150`, then `GH-150` |
| 2 Epic -> features | prose epic naming `pre_edit`, `Packer`, "init settings writer" | `Packer` missed (not CamelCase), prose module not resolved | exact-resolve filter lets Capitalised and `_private` names through; prose stays unresolved (no `get_domain_impact_subgraph`) |
| 3 Issue -> PR | `fix devkb/hook.py:60 ...` | bypassed, as the gating rule says | none needed |
| 3 Issue -> PR | `fix _seen in the hook` | `_seen` missed; no tests in the bundle | `_seen` found; the bundle lists tests that call each symbol (top 2 symbols) |
| 4 CR -> PR | review feedback on this branch | blast radius correct (`init.py:277` calls `cli.main`; tests right); 1.4 KB footer per pack overflowed the budget | footer and title dropped |
| 5 Release | "prepare the release" | "SemVer suggests patch" for 11 commits that use `area:` not `feat/fix`: a guess | no verdict when no commit is typed; shows the range by area |
| 5 Release | "release the lock ..." | would have routed to release | trigger needs a release phrase |
| End to end | `claude -p`, no tools, hook on vs `DEVKB_ROUTER=0` | on: `devkb/hook.py:73` + `tests/test_devkb_hook.py` (both correct); off: NO CONTEXT | none |

Defects in the graph itself, found on the way and not fixed here (AGENTS.md rule 5: one issue each): `pack error` lists
raisers whose files do not contain the message, without a Coverage warning; `tests_for` shows 2 of 6+ test files for
`Packer` and says "no test calls it" for a function that tests reach only through its caller.
