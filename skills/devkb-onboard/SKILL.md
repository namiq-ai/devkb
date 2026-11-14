---
name: devkb-onboard
description: Use to understand an unfamiliar area of a repository that has the devkb-sdlc tools, before touching it. One call gives its key symbols, entry points, owners, documents, tests and recent activity.
---

# Understand an area

1. Call `explain_area` with a directory or file. Read the key symbols first: they are ordered by how much depends on them.
2. Use `find_code` with a plain-words query to locate a behaviour by name and docstring, instead of searching blindly.
3. Read the governing documents it lists, then the entry points, then one test.
   For how it runs, call `config`: with no query it lists services and settings; with a setting name it shows the code that reads it, the files that declare it and the services that deploy those files, across the product's repositories.
4. Write down in two sentences what the area does and who owns it. If you cannot, ask for the missing document.

Limits: the graph knows names, calls and history, not intent. The documents are where intent lives.
