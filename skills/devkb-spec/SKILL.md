---
name: devkb-spec
description: Use when writing a functional design, architecture design, detailed design or sequence diagram in a repository that has the devkb-sdlc tools. One call gives the sections, the facts to cite, the documents to align with and the next free spec id.
---

# Write a design or specification

1. Call `design_brief` with the kind (`functional`, `architecture`, `detailed`, `sequence`) and the topic in plain words. It returns the outline, the front matter, the next free `SPEC-` id, the existing documents on the topic with their headings, the code, interfaces and errors to cite, similar past work and the owners.
2. For a sequence diagram, call `flow_sequence` on the entry point: it returns the recorded call order and Mermaid text to start from.
3. Write every factual sentence with its source: a path, a `path::function` or an ADR id. Leave a gap marked `TODO: verify` rather than inventing.
4. Before handing over, call `review_doc` on your document with the same kind and fix what it lists.

Limits: the graph knows structure and history, not intent. Requirements and decisions come from people and documents.
