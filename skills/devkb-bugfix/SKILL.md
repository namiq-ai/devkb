---
name: devkb-bugfix
description: Use when fixing a bug from a ticket in a repository that has the devkb-sdlc tools. One call returns the suspects, the history of those files, similar past bugs and the tests that guard them.
---

# Fix a bug from a ticket

1. Call `bug_brief` with the ticket id (or the symptom text). It returns suspect code (by error message and by name), the recent commits on those files, similar past bugs with the files that fixed them, and the tests that cover the suspects.
2. Read the top suspect and the test that covers it. Reproduce with that test or write the failing one first.
3. Fix at the cause, not at the symptom. Check `similar_bugs`: if the same shape was fixed elsewhere, fix the siblings too.
4. Run what `tests_to_run` names for your files, and quote the output when you report.

Limits: suspects are candidates, not a diagnosis. A bug with no error text or distinctive name may return nothing useful; then search the code directly.
