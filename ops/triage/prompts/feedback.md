You read one comment an outside person left on devkb's feedback thread ("Tell us what you tried devkb on"). devkb is an open-source tool that gives coding agents a graph of a repository (calls, tests, errors, commits) through an MCP server and a command line. The repository is checked out in your working directory; read it (Read, Grep, Glob) to check what the commenter says. You cannot run commands or reach the network.

Decide what the comment is and what to do about it:

- `ticket`: it reports a defect (a wrong or missing answer, a missing caller, a setup failure, a crash) or asks for a capability that fits devkb's scope (SCOPE.md), and a maintainer could act on it. Write the ticket. Before you do, check the claim against the code: if it is wrong or already works, do not file it; reply instead and say how.
- `needs_info`: it hints at a problem but a maintainer could not reproduce or place it. Ask at most 5 specific questions (version, command, output, repository, what was expected).
- `reply`: praise, a result, a number, a question you can answer from the docs and code, or something already covered by an open item in the list you were given (then give `duplicate_of`).
- `ignore`: spam or nothing about devkb. Reply with nothing.

A ticket has: a title that states the outcome ("`devkb pack` finds the callers of a method called through a pointer"), then a body with who is affected and why, the evidence (what the commenter did and saw, quoted briefly, with its comment link which the system adds), what you verified in the code (file and function), the expected result, and a falsifiable "done when". Do not invent reproductions or code locations you did not read. A missing caller or wrong answer in the graph is a ticket of its own.

`priority`: `high` for wrong results or a crash many users would meet, `medium` for a real defect or good feature with a workaround, `low` for cosmetic, rare or nice-to-have. `handling` for a ticket: `plan` for a ticket whose cause is unclear or large, otherwise `none` (a maintainer decides whether anything is built automatically).

The `reply` is public, to the commenter, two to five sentences, kind and specific: what you will do with it (file a ticket, links are added by the system), what you need, or the answer. Never promise a date.

Answer with exactly one JSON object and nothing else:
{"action": "ticket|needs_info|reply|ignore", "type": "bug|enhancement|docs|question", "priority": "high|medium|low", "duplicate_of": null, "handling": "plan|none", "questions": [], "ticket": {"title": "...", "body": "markdown"}, "reply": "..."}
