# Working in this repository

Work efficiently. Prefer a few targeted searches to broad exploration, and read only the files you need to answer.

## Where to look, by kind of question

| Question | Where to look first |
|---|---|
| Who calls a function, what tests it | search for its name across the source and tests |
| Which role owns a path | the role profiles under sdp/process/roles, OWN and DO NOT TOUCH blocks |
| Which specs and decisions apply | docs/spec, docs/adr, design/ and backlogs/ |
| Is a story ready | the story's Trace table and the readiness gate script |
| What a commit changed | git show for the commit |
| How a ticket is linked | the ticket file in issues/ and git log with --grep |

## Rules

1. Search first, then read what the search names.
2. A short answer is not necessarily a complete one: for a deletion or signature change, search the whole repository.
3. Do not run scripts that decide on your behalf where a human or a gate decides.
4. Say what you relied on when you hand off or review.

## Output shape

Answer in the JSON shape the question asks for and nothing else.
