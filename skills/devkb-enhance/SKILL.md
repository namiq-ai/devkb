---
name: devkb-enhance
description: Use when changing or extending existing behaviour in a repository that has the devkb-sdlc tools. One call shows what depends on it, what tests it, who owns it and what changed recently.
---

# Enhance existing behaviour

1. Call `explain_area` with the file or directory you will change. It lists the key symbols (most depended on first), entry points, the owning role, governing documents, tests and recent changes.
2. Call `refactor_scope` on the one function you will change to see its callers by file, the endpoints and flows it reaches, and the tests to rerun.
3. Read the function and its tests, nothing else, unless a caller's contract changes.
4. Keep the old behaviour under test first; then change it; then run exactly the tests `tests_to_run` names for your files.

Limits: dynamic dispatch is not in the graph. For a signature change, confirm callers with a text search.
