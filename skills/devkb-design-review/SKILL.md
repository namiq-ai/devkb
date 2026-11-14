---
name: devkb-design-review
description: Use when reviewing a design, specification or test specification in a repository that has the devkb-sdlc tools. One call checks the document against the repository instead of reading both side by side.
---

# Review a design or test specification

1. Call `review_doc` with the document path and its kind (`functional`, `architecture`, `detailed`, `sequence`, `test_spec`). It returns references that do not exist (paths, functions, tickets, spec ids), files it describes that changed after it was written, important code it never mentions, missing sections, and for a test specification the untested items it leaves out.
2. Read the document once with that list beside you. Check each item; a stale reference may be a renamed file, not an error.
3. Report findings by severity: wrong (a broken reference or a contradiction), stale (drift), incomplete (missing section or unmentioned code).
4. Do not rewrite the document in a review. Say what must change and why.

Limits: it checks references and structure. Whether the design is right is your judgement.
