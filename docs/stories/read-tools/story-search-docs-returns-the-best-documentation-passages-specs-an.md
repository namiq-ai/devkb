---
id: 9
type: story
title: "search_docs returns the best documentation passages, specs and ADRs first"
parent: epic-core-read-tools
covers: [R8]
after: [2]
hitl: false
risk: low
---

# search_docs returns the best documentation passages, specs and ADRs first

## Description

D6. 9.6% of grep cost is a search in docs, specs and tickets; `find_docs` ranks documents by topic but returns no lines. `search_docs(query)` and `devkb docs QUERY` (ADR-DEVKB-010 section 6) return the matching lines of tracked `.md`, `.rst`, `.txt` and `.adoc` files with the nearest preceding heading.

## Requirements

1. **Specs and ADRs come first** (R8)
   **Given** FX-MIX with `docs/specs/SPEC-X.md`, `docs/adr/ADR-1.md` and `docs/notes.rst`, all holding the word `retry`
   **When** `search_docs retry` runs
   **Then** the spec and the ADR are listed before `docs/notes.rst`, even when the notes file has more matching lines

2. **Each hit carries its heading** (R8)
   **Given** `SPEC-X.md` with `## Retries` above the matching line
   **When** the reply is read
   **Then** the hit is `L<line>  under "Retries"  <line text>`; the same holds for an RST title with an underline and an AsciiDoc `=` heading; a hit above any heading says `top of file`

3. **Several terms rank files holding more of them first** (R8)
   **Given** the query `retry limit` and one file with both words, another with one
   **When** the search runs
   **Then** the file with both words is listed first within its group; a double-quoted phrase is one term

4. **Caps are those of uses and are reported** (R8)
   **Given** documents with 40 matching lines in 15 files
   **When** the search runs
   **Then** at most 12 files, 36 hits and 3 per file are shown and the last line states the totals and what was omitted

5. **Nothing is found, nothing is invented** (R8)
   **Given** a query that appears nowhere
   **When** the search runs
   **Then** the reply is `no documentation line holds "<query>"` and names the file types searched; generated and untracked paths are never searched

6. **The tool is registered and `find_docs` is unchanged** (R1)
   **Given** the MCP server with `--toolset lean-pack`, `dev`, `all` and `workflow`
   **When** the tool list is read
   **Then** `search_docs` is in the first three and not in `workflow`, and `find_docs` replies are byte-identical to before on FX-MIX

## Boundaries

- Must not change: `find_docs`, `sdlc_context`, `trace`.
- Not here: ticket files outside tracked documentation types.

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 2, 6
