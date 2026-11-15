<!-- devkb:begin (managed by `devkb init`; edit outside this block) -->
## devkb: before you change code

This repository has a graph of its code (calls, tests, raised errors, commits, configuration) in `.devkb/`. Use it at
these steps; each command prints the answer with the line of code that proves every item and says what it could not
see:

1. **Before you edit an existing file**, run `devkb pack --project . file PATH`: which of its functions other files
   call (your change must keep them working), the files that depend on it, and the tests that exercise it.
2. **Before you change a function's signature or behaviour**, run `devkb pack --project . refactor NAME` (every
   caller, tests among them) or `devkb pack --project . change NAME --path PATH` (callers at any depth, tests to run).
3. **When you start from an error message**, run `devkb pack --project . error "MESSAGE"`.
4. **After editing**, run the tests the pack named first, then the full suite.
5. If you edited many files, rebuild first: `devkb build --project .` (a few seconds on most repositories).

The same graph is served by the `devkb` MCP server for questions in between:

| Question | Use |
|---|---|
| An area you have not read: its files, key functions, tests, docs | `explain_area` with the folder |
| Where a new feature or change belongs: related code, docs, tests | `feature_brief` with the goal |
| Code that does something, found by what it does | `find_code` |
| Who calls a function / the impact of a change | `callers` / `impact` |
| Which tests to run | `tests_to_run`, or `tests_for` a file or function |
| A commit or a diff to review | `review_pack` |
| A setting or a service | `config` |

Rules: a pack or answer marked **Complete** is the whole answer: do not search again. If it is incomplete, search only
the files it names. If it says files changed since the graph was built, re-read those files.
<!-- devkb:end -->
