---
name: devkb-lean-pack
description: Use when the devkb-sdlc lean tools and the pack tool are loaded: ask for a whole answer first (a file before editing, a function before changing it, an error), then use the single tools only for what the pack leaves open.
---

# A whole answer first, then the graph's single tools

- **Start with `pack`**: `pack(kind="refactor", subject=NAME)` for who calls a function, `pack(kind="change", subject=NAME, path=FILE)` for callers at any depth and the tests to run, `pack(kind="error", subject=MESSAGE)` for the route handlers that reach an error, `pack(kind="file", subject=PATH)` before editing a file. One call returns the answer, each item with the line that proves it.
- If its Coverage says **Complete**, the pack is the answer: do not re-search. If it says Incomplete, search only where it points.
- For what a pack does not cover: `rca_trace`, `impact`, `callers`, `tests_for`, `tests_to_run`, `review_pack`, `config`.
- If `_meta.stale` is true, re-read the files that decide the change.
