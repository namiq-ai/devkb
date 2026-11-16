---
name: devkb-lean-pack
description: Use when the devkb-sdlc lean tools and the pack tool are loaded: ask for a whole answer on a question that follows a chain (a file before editing, a change, an error), and search as usual for a one-hop lookup.
---

# A whole answer for a chain, a search for one hop

- **For a chain, start with `pack`**: `pack(kind="change", subject=NAME, path=FILE)` for callers at any depth and the tests to run, `pack(kind="error", subject=MESSAGE)` for the route handlers that reach an error, `pack(kind="file", subject=PATH)` before editing a file. One call returns the answer, each item with the line that proves it.
- **For one hop, search**: who calls one function directly is a single grep; a pack adds a step (measured: packs saved 66-77% on chains and cost more than search on one-hop lookups).
- If a pack's Coverage says **Complete**, it is the answer: do not search again or call `callers` to check it. If it says Incomplete, search only where it points.
- For what a pack does not cover: `rca_trace`, `impact`, `callers`, `tests_for`, `tests_to_run`, `review_pack`, `config`.
- If `_meta.stale` is true, re-read the files that decide the change.
