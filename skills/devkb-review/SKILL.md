---
name: devkb-review
description: Use when reviewing a commit, range or pull request in a repository that has the devkb-sdlc tools. One call gives the changed functions, callers outside the diff, tests, untested changes, governing documents and owners.
---

# Review a change

1. Call `review_pack` with the commit or `base..head`. It returns the changed functions, their callers outside the diff, the tests that cover them, the changed functions with no test, the documents governing the tickets named in the commit, rule warnings on the files and the owning roles.
2. Read the diff. Then read only the callers outside the diff that the change could break.
3. Report: what changed, who else it reaches, what is untested, whether any file belongs to a role other than the author's.
3a. When the change is a pull request (`PR-12`, or `pull_requests` in the reply), call `pull_request` with its number: its commits, the functions it changed, tests to run and the issues it closes. Read its `coverage`: a link marked unverified, or a build without GitHub, means the issue links may be incomplete.
4. If `drift` is listed, those files changed after the graph was built; trust names, re-check lines.

Limits: it describes structure, not correctness. A clean pack is not an approval.
