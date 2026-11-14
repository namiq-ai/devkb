---
name: devkb-testspec
description: Use when writing a test specification or test items in a repository that has the devkb-sdlc tools. One call derives test items from what the code raises, the endpoints it serves and the branchy functions nobody tests.
---

# Write a test specification

1. Call `test_items` with the path, directory or function. It returns candidate items: one negative test per error the code raises, one contract test per endpoint, one branch test per untested function with complexity 3 or more, each marked covered or not, plus the existing tests and register cases.
2. Call `design_brief` with kind `test_spec` for the outline and the documents to trace to.
3. Write each case as id, steps and expected result, and link it to the item and the requirement. Uncovered items first.
4. Call `review_doc` with kind `test_spec`: it lists untested items your document does not mention.

Limits: items come from structure. Business scenarios a person cares about still need the requirement and the user.
