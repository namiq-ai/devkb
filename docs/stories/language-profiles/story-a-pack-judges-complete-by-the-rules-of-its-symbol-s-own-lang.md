---
id: 4
type: story
title: "A pack judges Complete by the rules of its symbol's own language"
parent: epic-language-profiles
covers: [R4, R5]
after: [3]
hitl: false
risk: medium
---

# A pack judges Complete by the rules of its symbol's own language

## Description

Completeness today is one rule for both languages and one limit text that talks about overloads and receivers even for a C function. This story lets `_coverage` and `packs.py` read the symbol's `language` and give each profile its reasons and its limits.

## Requirements

1. **A C pack and a C++ pack state different limits** (R5)
   **Given** one C function and one C++ method in tests/fixtures/profiles/coverage
   **When** both packs are rendered
   **Then** the C pack names no overloads and no receivers and does name macro-generated definitions, function-pointer and ops-table calls; the C++ pack carries today's `CXX_LIMITS_TEXT`; a Python pack carries neither

2. **The reply says which profile judged it** (R5)
   **Given** `callers` for a C function with an ops-table reference
   **When** the JSON is read
   **Then** it has `complete` false, `profile` `c`, `reasons` containing `indirect-reference`

3. **A C symbol with no unresolved call is Complete under the C profile** (R5)
   **Given** a `static` C function called twice in its own file and referenced nowhere else
   **When** its pack is rendered
   **Then** it says Complete and carries the C limits

4. **The README test still holds** (R5)
   **Given** the README limits row
   **When** `pytest tests -k limits` runs
   **Then** each limit the README names is demonstrated by a fixture, for each profile

5. **Python packs and C++ packs are unchanged** (R4)
   **Given** the existing Python and C++ pack tests
   **When** they run
   **Then** they pass unchanged

## Boundaries

- Must not change: the Complete rule for Python symbols; the `incomplete_reasons` set of C++ (`dynamic-dispatch`, `implicit-call`, `unread-file`).
- Shared file: `packs.py` and `process_api.py` are also edited by epic 2 story 1, which adds the exported-symbol qualifier on top; this story owns the profile switch.

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-language-profiles/epic-language-profiles.md
- spec — docs/spec/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
