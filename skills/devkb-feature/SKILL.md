---
name: devkb-feature
description: Use when building a new feature from a requirement or ticket in a repository that has the devkb-sdlc tools. One call says where it belongs, what governs it, what to copy, who owns the area and what to run.
---

# New feature

1. Call `feature_brief` once with the goal in plain words (and the ticket id if there is one). It returns similar code, the specs and ADRs that govern the area, past tickets that did similar work, the owning role and the paths it must not touch, and the tests to copy and run.
2. Read only what it names: the top two or three code files and the governing documents.
3. Build inside the owner's paths. If the change needs a path another role owns, stop and say so; that is a ticket, not an edit.
4. Before you finish, call `tests_to_run` with the files you changed and run exactly that, then `impact` and state what else the change reaches.

Limits: similar code is matched by name and docstring, so confirm by reading. If `_meta.stale` is true, re-verify anything that decides the design.
