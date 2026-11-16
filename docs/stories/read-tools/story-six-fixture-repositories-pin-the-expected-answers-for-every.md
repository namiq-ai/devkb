---
id: 2
type: story
title: "Six fixture repositories pin the expected answers for every language"
parent: epic-core-read-tools
covers: [R9]
after: [1]
hitl: false
risk: low
---

# Six fixture repositories pin the expected answers for every language

## Description

Setup for every later story and for epic 2. It adds FX-TS, FX-CS, FX-C, FX-CPP and FX-MIX beside the FX-PY of story 1.1 (contents in ADR-DEVKB-010 section 9), each with a hand-written `expected.json` that no extractor produced, and builds the one capability table (`capability(path)`, ADR section 1) that every tool reads for range, separator and overload flags.

## Requirements

1. **Every fixture builds and agrees with its expected answers** (R9)
   **Given** `tests/fixtures/readtools/{py,ts,cs,c,cpp,mixed}/`, each with `expected.json` listing name, kind, start line, end line (absent for start-only languages) and direct caller count
   **When** `pytest tests/test_readtools_fixtures.py` runs
   **Then** each fixture builds with `devkb build --project <dir>`, and for every entry of its `expected.json` the graph holds a Symbol of that name and start line; for exact-range languages the end line equals the expected one; the test names each disagreement and fails

2. **The expected file records what the graph lacks** (R9)
   **Given** FX-TS, FX-CS and FX-CPP
   **When** `expected.json` is read
   **Then** it lists under `not_indexed` the C# constructor, the generic `Load<T>`, `ILoader`, the TypeScript class methods and the other definitions the analysis says are missing, and under `shared_node` the overloads; the test fails when the graph starts to hold one of them, so the file is revised with the fix

3. **The capability table equals the analysis matrix** (R9)
   **Given** `capability()` for one path per extension of ADR section 1
   **When** `pytest tests/test_readtools_capability.py` runs
   **Then** the range, separator, overload and start-line flags equal the ADR table row for row, an unknown extension returns `range=start-only`, and the test fails when a row is changed without the ADR

4. **A language is a row, not a branch** (R9)
   **Given** the read-tool modules
   **When** `git grep -nE '\.(py|ts|cs|cpp)\b' devkb/readtools/` (the new package) runs
   **Then** the only matches are in the capability table module

5. **Fixtures are synthetic and small** (C4)
   **Given** the six directories
   **When** `du -sk tests/fixtures/readtools` runs and the files are read
   **Then** the total is under 200 KB, no file holds a real name, address or secret, and any address is in RFC5737 space

## Boundaries

- Must not change: `tests/fixtures/` files other than `readtools/`; the graph build.
- Not here: any tool beyond what 1.1 built.

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-core-read-tools/epic-core-read-tools.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, sections 1, 8, 9
- analysis — docs/analysis/read-tools-analysis.md, section 5

## Notes

- Assumption: the package is `devkb/readtools/` with one module per tool and a `capability.py`; the names are the builder's to change, the single-table rule is not.
