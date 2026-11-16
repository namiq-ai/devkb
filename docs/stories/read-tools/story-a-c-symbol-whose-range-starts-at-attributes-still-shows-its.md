---
id: 4
type: story
title: "A C# symbol whose range starts at attributes still shows its signature line"
parent: epic-language-readiness
covers: [R10]
after: ["1.2", "1.7"]
hitl: false
risk: low
---

# A C# symbol whose range starts at attributes still shows its signature line

## Description

`line_start` is the name row for Python, C and C++, but for 44% of FluentValidation's C# symbols and 19% of MediatR's it is the node start, the row of the attributes or modifiers above the name. A tool that prints `line_start`'s text as the signature would print `[Fact]`. The signature is the first line holding the name within 5 lines from the start.

## Requirements

1. **The signature is the line holding the name** (R10)
   **Given** FX-CS `tests/LoaderTests.cs` where `[Fact]` is on the start line and the method name two lines below
   **When** `symbol LoadsDefaults` runs
   **Then** the record's signature is the method's declaration line, the range is still the stored `L<start>-<end>`, and the line `[Fact]` is not shown as the signature

2. **A name more than 5 lines below the start is moved** (R10)
   **Given** a copy of FX-CS where 8 lines of comments were inserted between the attribute and the name after the build
   **When** the symbol is requested
   **Then** the record says `moved` and has no signature, as in story 1.7

3. **The rule is the same for every language** (R10)
   **Given** FX-PY, FX-C and FX-CPP where `line_start` is the name row
   **When** `symbol` runs for every expected symbol
   **Then** the signature is `line_start`'s own line; the scan below the start is used only when that line lacks the name

## Boundaries

- Must not change: stored `line_start`.

## References

- parent — _bmad-output/initiative-read-tools-for-every-language/tickets/epic-language-readiness/epic-language-readiness.md
- decision — docs/adr/ADR-DEVKB-010_read-tools.md, section 3.3
- analysis — docs/analysis/read-tools-analysis.md, section 2 finding 4
