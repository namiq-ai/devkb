---
name: devkb-sdlc
description: Use during development of a repository that has the devkb-sdlc MCP server. Ask the dev-process graph first (ticket context, callers, tests to run, impact, owner, review pack) and read only the files it names, instead of exploring the repository.
---

# devkb-sdlc

A graph of this repository's tickets, specs, commits, symbols, calls and tests, served by
the `devkb-sdlc` MCP server. It answers in milliseconds and in a few hundred bytes. Use it
to decide **what to read**, not instead of reading.

## Which tool, at which stage

| Stage | Question | Tool |
|---|---|---|
| S0 Intake, S3 Requirements | Is there a similar or duplicate ticket? Which specs and ADRs touch this? | `sdlc_context`, `find_docs` |
| S1 Understand | Who calls this? What tests it? Who owns it? | `callers`, `tests_for`, `owner` |
| S4 Solutioning | Which decisions constrain this area? | `find_docs` with `kinds: ["adr"]` |
| S5 Backlog, S6 Readiness | Is the chain requirement, spec, epic, story complete? | `trace` (the verdict mirrors Gate 0; `make gate-0` decides) |
| S7 Build | What does this change reach? Which tests to run? May my role touch this path? | `impact`, `tests_to_run`, `owner` |
| S8 Review | What changed, who calls it outside the diff, what is untested? | `review_pack` |
| S9, S10 Close, Knowledge | Lineage, duplicates, blockers of a ticket; the pull requests that closed it | `lineage`, `pull_request` |

## Rules

1. **Graph first, then read what it names.** One call usually replaces a search across the repository.
2. **Check `_meta.stale`.** If `true`, the repository has moved past the commit the graph was built at
   (`_meta.behind` commits). Trust ids and structure, re-verify anything that decides a change by reading the file.
3. **A short answer is not a complete answer.** `callers` only sees calls the extractor resolves
   (module attributes, aliases, relative imports, path-loaded modules). Dynamic dispatch is missing.
   For a deletion or a signature change, confirm with a text search.
4. **Do not use it where a script decides.** Gate 0 is `make gate-0`; the graph's `trace` verdict is advisory.
5. **Say what you relied on.** In a review or hand-off, name the tool calls and whether the graph was stale.
6. **A whole task has its own skill**: devkb-feature, -enhance, -bugfix, -rca, -refactor, -review, -onboard,
   -spec, -testspec, -design-review, and devkb-roles to start a session as a role.

## Output shape

Replies are compact JSON: paths and `path::name` symbol keys, `n` for totals, `truncated: true` when a list was capped.
A reply with an `error` key names what to pass instead (for example the candidate symbols when a name is ambiguous).
