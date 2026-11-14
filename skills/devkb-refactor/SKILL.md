---
name: devkb-refactor
description: Use before refactoring, renaming or moving code in a repository that has the devkb-sdlc tools. One call gives every caller by file, the tests to run, the endpoints reached and which files your role may not touch.
---

# Refactor safely

1. Call `refactor_scope` on the function or file, with your role code if you know it. It returns callers grouped by file, whether the symbol is public, its complexity, the endpoints and flows it reaches, the tests to run before and after, and `blocked_files`: callers in paths your role must not edit.
2. If `blocked_files` is not empty, the refactor needs another role. Say so before editing anything.
3. Run the listed tests first, change in small steps, run them after each step.
4. Update every caller the scope lists, then confirm with one text search for the old name.

Limits: calls through variables, reflection or string names are not in the graph. The caller list is a floor, not a proof.
