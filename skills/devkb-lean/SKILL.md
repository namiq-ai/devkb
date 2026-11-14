---
name: devkb-lean
description: Use when the devkb-sdlc lean tools are loaded and the work follows a call chain or joins code to tests: a root cause from an error, the impact of a change, the tests to run, a review of a commit.
---

# Chains and joins from the graph

Use the graph only where it saves several searches; a one-hop lookup is faster with grep.

- Error message to its cause: `rca_trace`. Change impact and its route handlers: `impact`. Who calls a function: `callers`. Tests to run: `tests_to_run` or `tests_for`. A commit or diff: `review_pack`. A setting or a service: `config`.
- Every list answer has `coverage`. If `complete` is true, the list is the answer: do not re-search. If false, search only the `search_files` it names.
- If `_meta.stale` is true, re-read files that decide the change.
