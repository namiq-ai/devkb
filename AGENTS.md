<!-- devkb:begin (managed by `devkb init`; edit outside this block) -->
## devkb: this repository's process graph

A graph of this repository (calls, tests, raised errors, commits, configuration) is served by the `devkb` MCP server
and built into `.devkb/` by `devkb build --project .`. Use it where it saves several searches; a one-hop lookup is
faster with grep.

| Question | Use |
|---|---|
| Before writing code in an area you have not read: its files, key functions, tests, docs | `explain_area` with the folder |
| Where a new feature or change belongs: related code, docs, past work, tests to run | `feature_brief` with the goal |
| Code that does something, found by what it does | `find_code` |
| An error message: where it is raised and what reaches it | `rca_trace` |
| The impact of changing a function: its callers at any depth, route handlers, tests | `impact` |
| Who calls a function | `callers` |
| Which tests to run for a change | `tests_to_run`, or `tests_for` a file or function |
| A commit or a diff to review | `review_pack` |
| A setting or a service: who reads it, where it is declared and deployed | `config` |

Rules:
- Every list answer carries `coverage`. If `complete` is true, the list is the answer: do not search again. If it is
  false, search only the files it names in `search_files`.
- If an answer's `_meta.stale` is true, the graph is older than the working tree: re-read the files that decide the
  change.
- Before a change, a whole answer in one step: `devkb pack --project . refactor NAME`, `devkb pack --project . change
  PATH`, `devkb pack --project . error "MESSAGE"`. A pack gives every item with the line of code that proves it and
  says what it could not see.
<!-- devkb:end -->
