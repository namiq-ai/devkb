---
name: devkb-rca
description: Use for root-cause analysis of a failure in a repository that has the devkb-sdlc tools. Turn an error message, symbol or endpoint into the raising code, the path that reaches it and the commits that changed that path.
---

# Root-cause analysis

1. Call `rca_trace` with the error text, symbol or endpoint. It returns where the message is raised or logged, the callers up to the entry points, the recent commits on every file in that chain (newest first, with ticket ids) and the tests that cover the raiser.
2. Start with the newest commit on the nearest file (`history` lists more for any files). Read that diff, not the whole file.
3. State the cause as a chain: entry point, the call that carries the bad input, the line that fails, the commit that introduced it.
4. Say what you have not verified. The graph shows what changed and what calls what, not why.

Limits: message templates replace values with `{}`, so search by the fixed words. If no signature matches, say so and fall back to a text search.
