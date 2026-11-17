---
name: devkb-lean-pack
description: Use when about to read a file to judge what depends on it, edit a file, change a function, or start from an error message, in a repository with a devkb graph (a .devkb folder) and the devkb tools. One call returns callers at any depth, dependent files and tests to run, each with its proof line. Not for one-hop lookups or for learning how code is written.
---

# Ask the graph first, then read

`pack` answers a whole question; choose by what you are about to do:

- **Open or edit a file**: `pack(kind="file", subject=PATH)` returns the functions other files call, the dependent files and the tests to run. Run it before your first edit of each file; the Claude Code hook also adds it then.
- **Change a function's behaviour or signature**: `pack(kind="change", subject=NAME, path=FILE)` returns callers at any depth and the tests.
- **Start from an error message**: `pack(kind="error", subject="MESSAGE")` returns what raises it and the handlers that reach it.
- **One hop** or **how a pattern is written**: grep or read the file.

If Coverage says **Complete**, it is the answer: do not search again or call `callers` to check it. If Incomplete, search only where it points. For the rest: `rca_trace`, `impact`, `callers`, `tests_for`, `tests_to_run`, `review_pack`, `config`. If `_meta.stale` is true, re-read the files that decide the change.
- **To read code, ask before you grep**: `symbol` (a definition's lines; `source=True` for its body; names, globs, `re:`, typos tolerated), `outline` (a file's shape), `uses` (where a name appears), `search_docs`.
